import base64
import json
from datetime import datetime, timedelta

import httpx
import pytest

from database.connection import get_cursor
from services import bank_feed


PUBLIC_IP = "93.184.216.34"
ACCESS_URL = "https://public.example/simplefin-access"


class Response:
    def __init__(self, status_code=200, text="", payload=None):
        self.status_code = status_code
        if payload is not None:
            self.content = json.dumps(payload).encode()
        else:
            self.content = text.encode()
        self.encoding = "utf-8"
        self._payload = payload

def _public_dns(monkeypatch):
    monkeypatch.setattr(
        bank_feed.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (bank_feed.socket.AF_INET, bank_feed.socket.SOCK_STREAM, 6, "", (PUBLIC_IP, 443))
        ],
    )


def _token(url="https://public.example/claim"):
    return base64.b64encode(url.encode()).decode()


def _link(client_id, bank_account_id, fake_credential_vault):
    secret_name = "simplefin.test.connection"
    fake_credential_vault[secret_name] = ACCESS_URL
    with get_cursor(commit=True) as cursor:
        cursor.execute(
            """INSERT INTO bank_connections
               (client_id, bank_account_id, provider, secret_name)
               VALUES (?, ?, 'simplefin', ?)""",
            (client_id, bank_account_id, secret_name),
        )
        return cursor.lastrowid


def _payload(transaction_id="txn-1", posted=None):
    posted = posted or int(datetime.now().timestamp())
    return {
        "accounts": [{
            "id": "remote-checking",
            "transactions": [{
                "id": transaction_id,
                "posted": posted,
                "amount": "-12.34",
                "description": "Office supplies",
            }],
        }],
    }


def test_claim_simplefin_token_success(monkeypatch):
    _public_dns(monkeypatch)
    calls = []

    def request(method, url, **kwargs):
        calls.append((method, kwargs))
        return Response(text=ACCESS_URL)

    monkeypatch.setattr(bank_feed.httpx, "request", request)
    assert bank_feed.claim_simplefin_token(_token()) == ACCESS_URL
    assert calls == [("POST", {
        "follow_redirects": False,
        "timeout": bank_feed.REQUEST_TIMEOUT,
    })]


def test_claim_simplefin_token_reclaim_is_user_safe(monkeypatch):
    _public_dns(monkeypatch)
    monkeypatch.setattr(
        bank_feed.httpx, "request", lambda *args, **kwargs: Response(status_code=410),
    )
    with pytest.raises(bank_feed.BankFeedError, match="already been claimed") as exc:
        bank_feed.claim_simplefin_token(_token())
    assert "https://" not in str(exc.value)


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.8", "169.254.2.3", "::1"])
def test_claim_rejects_special_use_destinations_before_request(
    monkeypatch, address,
):
    family = bank_feed.socket.AF_INET6 if ":" in address else bank_feed.socket.AF_INET
    monkeypatch.setattr(
        bank_feed.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (family, bank_feed.socket.SOCK_STREAM, 6, "", (address, 443))
        ],
    )
    requested = False

    def request(*args, **kwargs):
        nonlocal requested
        requested = True

    monkeypatch.setattr(bank_feed.httpx, "request", request)
    with pytest.raises(bank_feed.BankFeedError, match="not permitted"):
        bank_feed.claim_simplefin_token(_token())
    assert requested is False


def test_second_sync_overlap_deduplicates_remote_transaction(
    client_id, accounts, fake_credential_vault, monkeypatch,
):
    connection_id = _link(client_id, accounts["cash"], fake_credential_vault)
    starts = []

    def request(method, url, **kwargs):
        starts.append(kwargs["params"]["start-date"])
        return Response(payload=_payload())

    _public_dns(monkeypatch)
    monkeypatch.setattr(bank_feed.httpx, "request", request)
    assert len(bank_feed.sync_bank_feed(client_id, accounts["cash"])) == 1

    prior_watermark = (datetime.now().astimezone() - timedelta(days=1)).isoformat(
        timespec="seconds"
    )
    with get_cursor(commit=True) as cursor:
        cursor.execute(
            "UPDATE bank_connections SET last_synced_at = ? WHERE id = ?",
            (prior_watermark, connection_id),
        )

    assert bank_feed.sync_bank_feed(client_id, accounts["cash"]) == []
    assert starts[1] == (
        datetime.fromisoformat(prior_watermark).date() - timedelta(days=7)
    ).isoformat()
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM imported_transactions WHERE client_id = ?",
            (client_id,),
        )
        assert cursor.fetchone()[0] == 1


def test_sync_failure_rolls_back_staged_rows_watermark_and_audits(
    client_id, accounts, fake_credential_vault, monkeypatch,
):
    connection_id = _link(client_id, accounts["cash"], fake_credential_vault)
    _public_dns(monkeypatch)
    monkeypatch.setattr(
        bank_feed.httpx, "request",
        lambda *args, **kwargs: Response(payload=_payload()),
    )
    real_write = bank_feed.AuditLog.write

    def fail_watermark(cursor, client_id, table_name, record_id, action, **kwargs):
        if table_name == "bank_connections" and action == "UPDATE":
            raise RuntimeError("simulated mid-sync failure")
        return real_write(
            cursor, client_id, table_name, record_id, action, **kwargs,
        )

    monkeypatch.setattr(bank_feed.AuditLog, "write", fail_watermark)
    with pytest.raises(RuntimeError, match="simulated mid-sync failure"):
        bank_feed.sync_bank_feed(client_id, accounts["cash"])

    with get_cursor() as cursor:
        cursor.execute(
            "SELECT last_synced_at, sync_window_start FROM bank_connections WHERE id = ?",
            (connection_id,),
        )
        connection = cursor.fetchone()
        assert connection["last_synced_at"] is None
        assert connection["sync_window_start"] is None
        cursor.execute(
            "SELECT COUNT(*) FROM imported_transactions WHERE client_id = ?",
            (client_id,),
        )
        assert cursor.fetchone()[0] == 0
        cursor.execute(
            "SELECT COUNT(*) FROM audit_log WHERE table_name IN "
            "('bank_connections', 'imported_transactions')",
        )
        assert cursor.fetchone()[0] == 0


def test_connection_and_sync_audits_contain_no_credentials(
    client_id, accounts, fake_credential_vault, monkeypatch,
):
    _public_dns(monkeypatch)
    responses = iter([
        Response(text=ACCESS_URL),
        Response(payload=_payload()),
    ])
    monkeypatch.setattr(
        bank_feed.httpx, "request", lambda *args, **kwargs: next(responses),
    )
    bank_feed.create_bank_connection(client_id, accounts["cash"], _token())
    bank_feed.sync_bank_feed(client_id, accounts["cash"])
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT old_values, new_values FROM audit_log "
            "WHERE table_name IN ('bank_connections', 'imported_transactions')"
        )
        rendered = " ".join(
            f"{row['old_values'] or ''} {row['new_values'] or ''}"
            for row in cursor.fetchall()
        )
    assert "https://" not in rendered
    assert ACCESS_URL not in rendered
