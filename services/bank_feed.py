"""Manual SimpleFIN synchronization into the existing import inbox."""
import base64
import binascii
import ipaddress
import json
import socket
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit, urlunsplit

import httpx

from database.connection import get_connection, get_cursor
from models.account import Account
from models.audit_log import AuditLog
from models.transaction import ImportedTransaction
from services.import_identity import (
    classify_import_duplicates,
    ensure_import_identity,
)
from utils import secure_store


PROVIDER = "simplefin"
FIRST_SYNC_DAYS = 85
OVERLAP_DAYS = 7
REQUEST_TIMEOUT = 30.0


class BankFeedError(RuntimeError):
    """A user-safe bank-feed failure with no credential details."""


def _decode_setup_token(setup_token: str) -> str:
    token = (setup_token or "").strip()
    if not token:
        raise BankFeedError("Enter a SimpleFIN setup token.")
    try:
        padded = token + "=" * (-len(token) % 4)
        decoded = base64.b64decode(padded, altchars=b"-_", validate=True)
        return decoded.decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise BankFeedError("The SimpleFIN setup token is invalid.") from exc


def _validate_outbound_url(value: str) -> str:
    """Require a public HTTPS destination before every request.

    Redirect following is disabled on all requests, so no redirect hop can
    bypass this validation.
    """
    try:
        parsed = urlsplit(value)
        port = parsed.port or 443
    except (TypeError, ValueError) as exc:
        raise BankFeedError("The bank feed destination is invalid.") from exc
    if (parsed.scheme.lower() != "https" or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.fragment):
        raise BankFeedError("The bank feed destination is not permitted.")
    try:
        addresses = socket.getaddrinfo(
            parsed.hostname, port, type=socket.SOCK_STREAM,
        )
    except OSError as exc:
        raise BankFeedError("The bank feed destination could not be resolved.") from exc
    if not addresses:
        raise BankFeedError("The bank feed destination could not be resolved.")
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address[4][0])
        except ValueError as exc:
            raise BankFeedError("The bank feed destination is not permitted.") from exc
        if not ip.is_global:
            raise BankFeedError("The bank feed destination is not permitted.")
    return value


def _request(method: str, url: str, **kwargs):
    _validate_outbound_url(url)
    try:
        response = httpx.request(
            method, url, follow_redirects=False, timeout=REQUEST_TIMEOUT, **kwargs,
        )
    except httpx.HTTPError as exc:
        raise BankFeedError("SimpleFIN could not be reached. Try again later.") from exc
    if 300 <= response.status_code < 400:
        raise BankFeedError("SimpleFIN returned an unexpected redirect.")
    return response


def _response_text(response) -> str:
    try:
        content = response.content
    except (AttributeError, httpx.HTTPError) as exc:
        raise BankFeedError("SimpleFIN returned an unreadable response.") from exc
    try:
        return content.decode(response.encoding or "utf-8").strip()
    except (LookupError, UnicodeDecodeError) as exc:
        raise BankFeedError("SimpleFIN returned an unreadable response.") from exc


def _response_json(response):
    try:
        content = response.content
    except (AttributeError, httpx.HTTPError) as exc:
        raise BankFeedError("SimpleFIN returned unreadable data.") from exc
    try:
        return json.loads(content)
    except (UnicodeDecodeError, ValueError) as exc:
        raise BankFeedError("SimpleFIN returned unreadable data.") from exc


def claim_simplefin_token(setup_token: str) -> str:
    """Exchange a single-use setup token for a permanent access URL."""
    claim_url = _decode_setup_token(setup_token)
    response = _request("POST", claim_url)
    if response.status_code in (400, 401, 403, 404, 409, 410):
        raise BankFeedError(
            "This SimpleFIN setup token is invalid or has already been claimed."
        )
    if response.status_code != 200:
        raise BankFeedError("SimpleFIN could not link the account. Try again later.")
    access_url = _response_text(response)
    _validate_outbound_url(access_url)
    return access_url


def create_bank_connection(
    client_id: int, bank_account_id: int, setup_token: str,
) -> int:
    """Claim and securely store a SimpleFIN credential for one ledger account."""
    account = Account.get_by_id(bank_account_id, client_id)
    if account is None or account.type not in ("Asset", "Liability"):
        raise BankFeedError("Choose a bank or credit-card account for this client.")
    access_url = claim_simplefin_token(setup_token)
    secret_name = f"simplefin.connection.{uuid.uuid4().hex}"
    secure_store.set_secret(secret_name, access_url)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        cursor.execute(
            """INSERT INTO bank_connections
               (client_id, bank_account_id, provider, secret_name)
               VALUES (?, ?, ?, ?)""",
            (client_id, bank_account_id, PROVIDER, secret_name),
        )
        connection_id = cursor.lastrowid
        AuditLog.write(
            cursor, client_id, "bank_connections", connection_id, "INSERT",
            new_values={
                "bank_account_id": bank_account_id,
                "provider": PROVIDER,
            },
        )
        conn.commit()
        return connection_id
    except Exception:
        conn.rollback()
        secure_store.delete_secret(secret_name)
        raise
    finally:
        conn.close()


def list_bank_connections(client_id: int) -> list[dict]:
    with get_cursor() as cursor:
        cursor.execute(
            """SELECT bc.id, bc.client_id, bc.bank_account_id, bc.provider,
                      bcs.synced_at AS last_synced_at,
                      bcs.sync_window_start, bc.created_at,
                      a.account_number, a.name AS account_name
               FROM bank_connections bc
               JOIN accounts a ON a.id = bc.bank_account_id
                              AND a.client_id = bc.client_id
               LEFT JOIN bank_connection_syncs bcs
                      ON bcs.id = (
                          SELECT MAX(latest.id)
                          FROM bank_connection_syncs latest
                          WHERE latest.connection_id = bc.id
                      )
               WHERE bc.client_id = ? ORDER BY bc.id""",
            (client_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


def _connection(client_id: int, bank_account_id: int):
    with get_cursor() as cursor:
        cursor.execute(
            """SELECT bc.id, bc.client_id, bc.bank_account_id, bc.provider,
                      bc.secret_name, bc.created_at,
                      bcs.synced_at AS last_synced_at,
                      bcs.sync_window_start AS sync_window_start
               FROM bank_connections bc
               LEFT JOIN bank_connection_syncs bcs
                      ON bcs.id = (
                          SELECT MAX(latest.id)
                          FROM bank_connection_syncs latest
                          WHERE latest.connection_id = bc.id
                      )
               WHERE bc.client_id = ? AND bc.bank_account_id = ?
                 AND bc.provider = ?""",
            (client_id, bank_account_id, PROVIDER),
        )
        row = cursor.fetchone()
    if row is None:
        raise BankFeedError("No SimpleFIN connection is linked to this account.")
    return dict(row)


def _start_date(connection: dict, now: datetime) -> date:
    if not connection["last_synced_at"]:
        return now.date() - timedelta(days=FIRST_SYNC_DAYS)
    try:
        last_synced = datetime.fromisoformat(connection["last_synced_at"])
    except ValueError as exc:
        raise BankFeedError(
            f"Connection {connection['id']} has an invalid sync watermark."
        ) from exc
    return last_synced.date() - timedelta(days=OVERLAP_DAYS)


def _accounts_url(access_url: str) -> str:
    parsed = urlsplit(access_url.rstrip("/"))
    path = f"{parsed.path}/accounts"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _fetch(access_url: str, start: date, connection_id: int) -> dict:
    response = _request(
        "GET", _accounts_url(access_url), params={"start-date": start.isoformat()},
    )
    if response.status_code != 200:
        raise BankFeedError(
            f"SimpleFIN sync failed for connection {connection_id}."
        )
    try:
        payload = _response_json(response)
    except BankFeedError as exc:
        raise BankFeedError(
            f"SimpleFIN returned invalid data for connection {connection_id}."
        ) from exc
    if not isinstance(payload, dict):
        raise BankFeedError(
            f"SimpleFIN returned invalid data for connection {connection_id}."
        )
    return payload


def _transaction_date(value, connection_id: int) -> date:
    try:
        return datetime.fromtimestamp(int(value)).astimezone().date()
    except (OverflowError, OSError, TypeError, ValueError) as exc:
        raise BankFeedError(
            f"SimpleFIN returned an invalid transaction date for connection "
            f"{connection_id}."
        ) from exc


def _map_rows(payload: dict, connection: dict) -> list[dict]:
    rows = []
    accounts = payload.get("accounts", [])
    if not isinstance(accounts, list):
        raise BankFeedError(
            f"SimpleFIN returned invalid data for connection {connection['id']}."
        )
    for remote_account in accounts:
        remote_id = str(remote_account.get("id", "")).strip()
        transactions = remote_account.get("transactions", [])
        if not remote_id or not isinstance(transactions, list):
            raise BankFeedError(
                f"SimpleFIN returned invalid data for connection {connection['id']}."
            )
        for position, transaction in enumerate(transactions, start=1):
            transaction_id = str(transaction.get("id", "")).strip()
            description = str(transaction.get("description", "")).strip()
            if not transaction_id or not description:
                raise BankFeedError(
                    f"SimpleFIN returned an incomplete transaction for connection "
                    f"{connection['id']}."
                )
            try:
                amount = float(Decimal(str(transaction.get("amount"))))
            except (InvalidOperation, TypeError, ValueError) as exc:
                raise BankFeedError(
                    f"SimpleFIN returned an invalid amount for connection "
                    f"{connection['id']}."
                ) from exc
            source_id = (
                f"{PROVIDER}:{connection['id']}:{remote_id}:{transaction_id}"
            )
            row = {
                "date": _transaction_date(transaction.get("posted"), connection["id"]),
                "description": description,
                "amount": amount,
                "client_id": connection["client_id"],
                "bank_account_id": connection["bank_account_id"],
                "source_id": source_id,
                "source_filename": "SimpleFIN",
                "source_row_number": 1,
                "_remote_position": position,
            }
            ensure_import_identity(
                row, connection["client_id"], connection["bank_account_id"],
            )
            rows.append(row)
    return rows


def sync_bank_feed(client_id: int, bank_account_id: int) -> list[dict]:
    """Fetch and atomically stage fresh SimpleFIN rows for human review."""
    connection = _connection(client_id, bank_account_id)
    access_url = secure_store.get_secret(connection["secret_name"])
    if not access_url:
        raise BankFeedError(
            f"The credential for connection {connection['id']} is unavailable."
        )
    now = datetime.now().astimezone()
    start = _start_date(connection, now)
    payload = _fetch(access_url, start, connection["id"])
    mapped = _map_rows(payload, connection)
    classify_import_duplicates(mapped, client_id)
    fresh = [row for row in mapped if not row.get("is_duplicate")]
    batch_id = f"simplefin-{connection['id']}-{now:%Y%m%d%H%M%S}"

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        staged = []
        for row in fresh:
            transaction = ImportedTransaction(
                client_id=client_id,
                import_batch=batch_id,
                transaction_date=row["date"],
                description=row["description"][:200],
                amount=row["amount"],
                bank_account_id=bank_account_id,
                status="Pending",
                source_id=row["source_id"],
                source_filename=row["source_filename"],
                source_row_number=row["source_row_number"],
                row_fingerprint=row["row_fingerprint"],
                idempotency_key=row["idempotency_key"],
            )
            transaction.save(conn=conn)
            staged.append({
                "id": transaction.id,
                "date": row["date"].isoformat(),
                "description": row["description"],
                "amount": row["amount"],
                "bank_account_id": bank_account_id,
                "source_id": row["source_id"],
                "import_batch": batch_id,
            })

        synced_at = now.isoformat(timespec="seconds")
        cursor.execute(
            """INSERT INTO bank_connection_syncs
               (connection_id, synced_at, sync_window_start)
               VALUES (?, ?, ?)""",
            (connection["id"], synced_at, start.isoformat()),
        )
        sync_id = cursor.lastrowid
        AuditLog.write(
            cursor, client_id, "bank_connection_syncs", sync_id, "INSERT",
            new_values={
                "connection_id": connection["id"],
                "last_synced_at": synced_at,
                "sync_window_start": start.isoformat(),
                "staged_count": len(staged),
            },
        )
        conn.commit()
        return staged
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
