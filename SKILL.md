---
name: bog-banking
description: >-
  Read-only access to a Bank of Georgia (BOG) Business Online account. Use
  whenever the user asks about their BOG bank account — balance, available
  funds, transactions, statements, spending, suppliers, payroll totals, cash
  flow, reconciliation, duplicates, unusual activity, or GEL/foreign-exchange
  rates. On first use the skill asks the user for their BOG API credentials,
  stores them locally, and reuses them afterward. Strictly READ-ONLY: it can
  never move money, create payments, or sign anything.
---

# BOG Banking (read-only)

Help the user understand and manage their Bank of Georgia **Business Online**
account through conversation. A bundled tool (`scripts/bog.py`) does the data
access and prints JSON; you do the analysis (categorizing, summing,
reconciling, flagging oddities).

## Hard rules
1. **Read-only, always.** Only run the `bog.py` commands listed here. Never
   send a payment, transfer, sign a document, or call any write endpoint —
   there is none. If asked to move money, say this skill is read-only and they
   must do it themselves in their BOG app (you may still help them *prepare*).
2. Treat financial data with care; summarize rather than dumping raw tables
   unless asked.
3. When you ask for credentials, **never echo the Client Secret back** in your
   replies, and don't print it. The tool stores it locally for you.

## Running the tool
```
python3 scripts/bog.py <command> [options]
```
Every run prints one JSON object: `command`, `mode` (`live`/`mock`), `ok`, and
either `data` or `error`+`message`. Parse it, then answer in plain language.

## Credential flow — DO THIS FIRST, every session that needs data

**Step 1 — check status:**
```
python3 scripts/bog.py whoami
```

**Step 2 — react to the result:**

- `error: "no_keys"` → no credentials yet. **Ask the user only for their Client
  ID and Client Secret** (not the IBAN yet). Where to get them: register an app
  at `bonline.bog.ge/admin/api` (choose **Client Credentials Flow**). Save by
  piping JSON on **stdin** (keeps the secret off the command line):
  ```
  python3 scripts/bog.py save-credentials <<'JSON'
  {"client_id":"<id>","client_secret":"<secret>"}
  JSON
  ```
  Then run `whoami` again to confirm the keys work, and continue below.

- `error: "invalid_credentials"` → the keys were rejected — **either** wrong keys
  **or** API access not activated by the user's BOG banker. Tell them both
  possibilities and **offer to re-enter** new keys (same `save-credentials`).
  Wipe first if needed: `python3 scripts/bog.py forget-credentials`.

- `ok: true` → credentials are valid.
  - If `data.accounts_configured` > 0 → accounts already set up; proceed to the
    user's request.
  - If it's `0` → no account yet, so set one up (next section). Do **not** run a
    bare `discover` and do **not** try to auto-find accounts — BOG has no
    account-list endpoint, so the IBAN must come from the user.

## Setting up accounts (ask one at a time)

BOG cannot list a company's accounts, so you collect IBANs from the user — one
at a time, only as many as they want:

1. Ask for **one** account IBAN (e.g. `GE..BG...`). It's **not secret** — it's on
   their statements/invoices and in their BOG app. Do NOT ask for currency.
2. Add it and detect its currencies + balances:
   ```
   python3 scripts/bog.py add-account --iban <IBAN>
   python3 scripts/bog.py discover --account <IBAN>
   ```
3. Show the discovered balances, then **ask: "Do you want to add another
   account?"**
   - **Yes** → repeat from step 1 with the next IBAN.
   - **No** → stop asking; continue with the account(s) stored.

Adding always MERGES (existing IBANs are kept). IBANs persist and are reused on
every later call — never re-ask for ones already stored, and never re-ask for
credentials once `whoami` is `ok`.

## Managing accounts later

- "add another account GE.." → `add-account --iban <IBAN>` then
  `discover --account <IBAN>` (then ask if they want yet another)
- "remove / forget account GE.." → `remove-account --iban <IBAN>`
  (only when the user explicitly asks)
- "what accounts do you have?" → `accounts`

## Read-only commands
| Command | Returns |
|---|---|
| `whoami` | Whether credentials exist and work |
| `add-account --iban GE.. [--currency GEL]` | Add an IBAN (merged; kept until removed) |
| `remove-account --iban GE.. [--currency GEL]` | Remove an IBAN (or just one currency) |
| `discover [--account IBAN] [--currencies GEL,USD]` | Probe stored IBANs' currencies, save them |
| `accounts` | The stored IBAN(s) + their currencies |
| `balance [--account IBAN] [--currency GEL]` | Available + current balance |
| `statement [--account IBAN] [--currency GEL] [--from YYYY-MM-DD] [--to YYYY-MM-DD]` | Transactions for a period (auto-paginates) |
| `today [--account IBAN] [--currency GEL]` | Today's intraday activity |
| `rates [--currency USD]` | NBG official + BOG commercial buy/sell |

**Default = everything.** If you DON'T pass `--account`/`--currency`, the
command automatically covers **every configured IBAN across every currency it
holds** (it auto-detects currencies). Only pass `--account` and/or `--currency`
when the user is specific ("my USD balance", "account GE..123"). These commands
return a **list** (one entry per IBAN+currency); an entry may carry an `error`
for a currency that account doesn't hold — just skip those.

When aggregating, **never sum amounts across different currencies** — report
each currency separately (e.g. GEL total and USD total).

### Examples
- "What's my balance?" → `balance` (covers all accounts + currencies)
- "My USD balance?" → `balance --currency USD`
- "Last month's transactions" → `statement --from 2026-05-01 --to 2026-05-31`
- "How much did I pay <supplier>?" → run `statement`, then filter/sum yourself.
- "Anything unusual?" → run `statement`, then flag duplicates, round numbers,
  new counterparties, unexpectedly large amounts.
- "USD rate?" → `rates --currency USD`

## Mock mode
Pass `--mock` (or set `BOG_MOCK=1`) to return realistic **sample data** with no
bank access — useful to demonstrate the skill before the user's credentials
are ready. Always tell the user when results are sample data.

## Presenting results
- Format money with thousands separators + 2 decimals (e.g. `18,430.75 GEL`).
- Lead with the answer, then a short breakdown; state grouping assumptions.
- For reconciliation, explicitly flag possible duplicates, unusually large
  amounts, new/unknown counterparties, and round-number payments.

See `reference/endpoints.md` for the underlying BOG endpoints.
