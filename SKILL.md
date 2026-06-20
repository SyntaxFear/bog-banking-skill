---
name: bog-banking-skill
description: >-
  Read-only access to a Bank of Georgia (BOG) Business Online account. Use
  whenever the user asks about their BOG bank account — balance, available
  funds, transactions, statements, spending, suppliers, payroll totals, cash
  flow, reconciliation, duplicates, unusual activity, or GEL/foreign-exchange
  rates. On first use the skill walks the user through getting their BOG API
  credentials, stores them locally, and reuses them afterward. Strictly
  READ-ONLY: it can never move money, create payments, or sign anything.
---

# BOG Banking Skill (read-only)

Help the user understand and manage their Bank of Georgia **Business Online**
account through conversation. A bundled tool (`scripts/bog.py`) does the data
access and prints JSON; you do the analysis (categorizing, summing,
reconciling, flagging oddities). Works in any `SKILL.md`-compatible agent
(Claude Code, Codex, and others).

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

## Every session: check status first
Before doing anything that needs data, run:
```
python3 scripts/bog.py whoami
```
- `ok: true` and `data.accounts_configured` > 0 → fully set up; go straight to
  the user's request. **Never re-ask for credentials or for IBANs already
  stored.**
- `ok: true` but `accounts_configured` is `0` → keys work, no account yet → do
  **Step 6** of onboarding (add an IBAN).
- `error: "no_keys"` → brand-new user → run the **First-time setup** below.
- `error: "invalid_credentials"` → keys rejected → see **Step 5** below.

## First-time setup (onboarding) — walk the user through this once

Be warm and go one step at a time. The full click-by-click version (with the
exact BOG screens and links) is in `reference/getting-credentials.md` — relay it
in your own words and give the user the links below.

**Step 1 — Explain & reassure.** Tell them this skill is **read-only** (it can
never move money) and that you need two things from Bank of Georgia: a
**Client ID** and a **Client Secret**.

**Step 2 — Log in.** Ask them to log in to their Business Bank at
**https://bonline.bog.ge/** with their Business Online credentials.

**Step 3 — Create the API key.** Have them open
**https://bonline.bog.ge/admin/api** and click **Add new**, then:
  - **Integration type** — choose **Client Credentials Flow** (the automatic
    type that authorizes with the Client ID + Client Secret, with no username
    or password).
  - **API client name** — any name (e.g. their internet-bank user, or
    `Banking Assistant`).
  - Confirm with the **one-time code (OTP)**.

**Step 4 — Copy the keys.** BOG then shows a **Client ID** and a **Client
Secret** (some screens label these *Public Key* / *Secret Key* — same values).
Ask the user to paste both, then save — pipe JSON on **stdin** so the secret
never hits the command line:
```
python3 scripts/bog.py save-credentials <<'JSON'
{"client_id":"<Client ID>","client_secret":"<Client Secret>"}
JSON
```
Never echo the Client Secret back.

**Step 5 — Confirm login.** Run `whoami` again.
  - `ok: true` → keys work. Continue to Step 6.
  - `error: "invalid_credentials"` → either the keys are wrong **or** API access
    hasn't been activated yet by the user's **BOG business banker**. Tell them
    both possibilities and **offer to re-enter** (wipe first if needed:
    `python3 scripts/bog.py forget-credentials`).

**Step 6 — Add their first account.** Ask for **one** account IBAN (e.g.
`GE..BG...`). It's on their statements and in their BOG app, and it's **not
secret**. Don't ask for the currency. Then:
```
python3 scripts/bog.py add-account --iban <IBAN>
python3 scripts/bog.py discover --account <IBAN>
```
`discover` auto-detects which currencies that IBAN holds (GEL/USD/EUR/GBP).

**Step 7 — Their first live result.** Run `balance` and present it nicely (see
*Presenting results*). Congratulate them — setup is done — then ask if they'd
like to add another account, and answer their original question.

> Want to demo before the keys are ready? `python3 scripts/bog.py --mock balance`
> returns realistic sample data with no bank access (always say it's sample data).

## Setting up / managing accounts later

BOG cannot list a company's accounts, so you collect IBANs from the user — one
at a time, only as many as they want. Adding always MERGES (existing IBANs are
kept). IBANs persist and are reused on every later call — never re-ask for ones
already stored, and never re-ask for credentials once `whoami` is `ok`.

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

See `reference/getting-credentials.md` for the full credential walkthrough and
`reference/endpoints.md` for the underlying BOG endpoints.
