# Counterparty fixtures and duplicate proposals

`tests.counterparty_fixtures.seed_counterparty_book()` drives the existing
`services.ar_ap` customer/vendor, invoice/bill posting, payment, payment-credit
application, and credit-memo services. It needs an active temporary database,
as provided by the pytest `db` fixture; no Streamlit session is needed.
All names and transactions are invented. A local `random.Random(seed)` controls
dates and amounts, with fixed calendar anchors and explicit application dates.

The default seed is 1729, with ten customers, ten vendors, and ten manual
journals. Each customer/vendor pair generates five balanced, two-line entries:
an invoice, a bill, two payments initially held on account, and an applied credit
memo. Subsequent customer/vendor credit applications do not create new journals.
Every sourced line is attributed; manual lines stay null. Expected coverage is
`10 * party_count / (10 * party_count + 2 * manual_count)`: **100/120 = 83.33%**
for the default book.

The performance case uses `party_count=1500, manual_count=2500`: **10,000
entries, 20,000 lines, 15,000 attributed lines (75%)**. It retains a substantial
manual slice and clears the original 50% threshold using actual counterparties.
The older `seed_journal_volume` fixture remains available for its existing tests.

Run the fixture and evaluation checks with:

```sh
.venv/bin/python -m pytest -q -s -p no:cacheprovider tests/test_counterparty_duplicates.py
```

Coverage and precision/recall are printed and attached as pytest properties.
`--junitxml=/tmp/counterparty-evaluation.xml -o junit_family=legacy` also exports
those properties, including all labelled entry pairs. Reproducibility means
the same business records and labels in a fresh book; generated book UUIDs,
audit session IDs, and wall-clock timestamps are excluded from that comparison.

Migration 909 adds nullable `journal_entry_lines.counterparty_id` and typed,
client-scoped identities in `counterparties`. `(kind, source_id)` is the source
link: customer IDs refer to `customers`, vendor IDs to `vendors`, and employee
IDs to `employees`; unlinked identities have a null source ID. Only AR/AP sources
are seeded/backfilled here. Identity links cannot be reassigned, and journal
lines cannot use another client's identity.

Backfill follows stored journal IDs on invoices, bills, both generations of
payments, refunds, credit memos, inventory sale/void movements, and explicit
reversal links. It does not infer a party from descriptions or names. Conflicting
party links are left null. New AR/AP postings set the identity before insertion;
reversals copy it. Posted-entry editing remains prohibited. The upgrade test
replays service-produced records into the pre-909 schema, then runs the normal
migration runner, checks financial records and foreign keys, and reruns it to
prove idempotence. It also covers legacy payment links, taxes, inventory,
refunds, credit/document/payment voids, and generic reversals.

`propose_duplicates(client_id, amount_tolerance_cents=1, date_window_days=3)`
is available through MCP at propose/post access levels. The candidate key is
counterparty, signed line amount within an inclusive integer-cent tolerance,
and an inclusive calendar-day window. Matching also requires the same account
and debit/credit direction. Results group matching lines by entry pair and party.
The supported bounds are 0–10,000 cents and 0–366 days.

Reversed entries and AR/AP void pairs are excluded. Distinct nonempty source
references or distinct AR/AP source records are treated as separate occurrences,
including payments whose generated journal text happens to be identical. This
conservative rule can miss real duplicates entered under different references;
missing attribution cannot produce a proposal. Returned proposals are transient
review results: there is no proposal persistence, approval action, or merge path.
The tool preserves the entire database. A human uses the existing reversal or
source-specific correction flow after reviewing a proposal.

The default evaluation seed is 2718. Eight repetitions of three positive cases
(exact amount, one-cent tolerance, three-day boundary) and seven negative cases
(AR/AP reversal, recurring charge, different party, two-cent difference,
four-day difference, opposite sign, missing attribution) produce **80 labelled
pairs: 24 positives and 56 hard negatives**. All proposals across the evaluation
book are scored; even an unlabelled cross-pair match counts as a false positive.
Empty output scores zero precision and recall. The oracle requires precision
at least **0.98** and reports recall; the seeded set currently scores **1.0 / 1.0**.
This measures the stated synthetic cases, not precision on arbitrary live books.
