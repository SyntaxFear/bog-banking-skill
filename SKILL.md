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

- `ok: true` → credentials are stored and valid. Proceed to the user's request.

- `error: "no_keys"` → no credentials yet. **Ask the user only for their Client
  ID and Client Secret** (don't ask for IBAN or currency yet). Tell them where
  to get them if needed: register an app at `bonline.bog.ge/admin/api` (choose
  **Client Credentials Flow**). Save by piping JSON on **stdin** (keeps the
  secret off the command line):
  ```
  python3 scripts/bog.py save-credentials <<'JSON'
  {"client_id":"<id>","client_secret":"<secret>"}
  JSON
  ```
  Then run **discover** — it logs in, tries to fetch the account list from BOG,
  and auto-detects each account's currencies:
  ```
  python3 scripts/bog.py discover
  ```
  - If `discover` returns accounts → show the user their accounts/balances and
    proceed. (No IBAN needed — BOG returned them, or they were already saved.)
  - If `discover` returns `error: "no_account"` → BOG has no account-list
    endpoint, so now ask the user for their **account IBAN** (e.g. `GE..BG...`;
    it's **not secret** — it's on their statements/invoices and in their BOG
    app; they can give several). Add each IBAN, then discover again:
    ```
    python3 scripts/bog.py add-account --iban <IBAN>
    python3 scripts/bog.py discover
    ```
    (Currency is auto-detected — never ask for it.)

## Managing accounts (persistent)

Stored IBANs **persist** and are reused on every call. Add or remove them
whenever the user asks — you don't re-ask for ones already stored:

- "add account GE.." / "also check my other account" →
  `python3 scripts/bog.py add-account --iban <IBAN>` then `discover`
  (adding MERGES — it never removes existing IBANs)
- "remove / forget account GE.." →
  `python3 scripts/bog.py remove-account --iban <IBAN>`
  (only delete when the user explicitly asks)
- "what accounts do you have?" → `python3 scripts/bog.py accounts`

- `error: "invalid_credentials"` → stored credentials were rejected. This means
  **either** the keys are wrong **or** the user's BOG API access isn't activated
  yet. Tell the user both possibilities, ask them to verify the keys and/or
  confirm activation with their banker, and **offer to re-enter** new
  credentials (same `save-credentials` step). To wipe stored credentials first:
  `python3 scripts/bog.py forget-credentials`.

Once `whoami` is `ok`, the credentials are reused automatically on every later
call — don't ask again.

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
