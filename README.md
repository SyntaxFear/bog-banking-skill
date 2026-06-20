# bog-banking-skill

[![version](https://img.shields.io/github/v/release/SyntaxFear/bog-banking-skill?sort=semver)](https://github.com/SyntaxFear/bog-banking-skill/releases)
[![license: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![read-only](https://img.shields.io/badge/access-read--only-blue)](#-security--privacy)

A **read-only Agent Skill** that lets an AI coding agent — **Claude Code**,
**Codex**, or any [`SKILL.md`](https://code.claude.com/docs/en/skills)-compatible
agent — read your **Bank of Georgia Business Online** account and help you
understand and manage your finances through plain conversation.

Ask things like *"what's my balance?"*, *"how much did I spend on suppliers last
month?"*, or *"anything unusual this week?"* — the agent fetches your real data
and reasons about it.

> 🔒 **Read-only by design.** It can never move money, create payments, or sign
> anything. It only *reads* (balances, statements, FX rates).

---

## ✨ What it can do

| Ability | What you get |
|---|---|
| **Balance & cash-flow** | Available + current balance across **every account and currency** you have |
| **Transactions / statements** | Full transaction history for any date range (auto-paginated) |
| **Spending analysis** | "How much did I pay supplier X?", grouping by counterparty/category, totals |
| **Reconciliation** | Spot duplicate payments, unusually large amounts, new/unknown counterparties |
| **Today's activity** | Intraday operations posted today |
| **Exchange rates** | NBG official rate + BOG commercial buy/sell + cross rates |
| **Multi-account** | Add several IBANs; by default it checks all of them in all currencies |

**What it deliberately does *not* do:** send payments, transfers, payroll, or
currency conversions; sign documents; or anything that changes your account. If
you ask it to move money, it will explain it can't — you do that yourself in
your BOG app.

---

## 🔑 Step 1 — Get your BOG API credentials

You need a **Client ID** and a **Client Secret** from Bank of Georgia (some BOG
screens call these the *Public Key* / *Secret Key* — same values). They're free
if you have a BOG **business** account with Business Internet Banking.

1. **Log in** to **[bonline.bog.ge](https://bonline.bog.ge/)** with your Business
   Online credentials.
2. Open the API admin page **[bonline.bog.ge/admin/api](https://bonline.bog.ge/admin/api)**
   and click **Add new**.
3. Choose the integration type **Client Credentials Flow** (the automatic type —
   it authorizes with the Client ID + Client Secret, with no username/password),
   give the **API client name** any value, and confirm with the **one-time code
   (OTP)**.
4. BOG then shows your **Client ID** and **Client Secret** — copy both. The
   secret is shown once; keep it safe.

> ⚠️ **If login later fails with `invalid_credentials`:** double-check the keys,
> and ask your **BOG business banker to enable API access** for your application
> — on some accounts API access must be switched on before the keys work.

You'll paste these into the agent on first use (see Step 3). You do **not** put
them in any file — the skill stores them in your OS keychain. Full walkthrough:
[reference/getting-credentials.md](reference/getting-credentials.md).

---

## 💻 Step 2 — Install the skill (one line)

```bash
curl -fsSL https://raw.githubusercontent.com/SyntaxFear/bog-banking-skill/main/install.sh | bash
```

That's it — no clone needed. It installs into both tools:
- **Claude Code** → `~/.claude/skills/bog-banking-skill/`
- **Codex** → `~/.agents/skills/bog-banking-skill/`

**Pin to a released version** (recommended for production):
```bash
curl -fsSL https://raw.githubusercontent.com/SyntaxFear/bog-banking-skill/main/install.sh | BOG_SKILL_REF=v1.1.0 bash
```

> 🔎 **Trust note:** the plain one-liner runs the current `main` branch
> (unpinned, unsigned) over HTTPS. Pin a version (above) or use the clone method
> below and inspect `install.sh` and `scripts/bog.py` before running.

<details>
<summary>Prefer to clone first, or inspect before running?</summary>

```bash
git clone https://github.com/SyntaxFear/bog-banking-skill.git
cd bog-banking-skill
bash install.sh
```

Or copy the folder into your agent's skills directory manually — works for any
`SKILL.md`-compatible agent. On Windows, place it in your tool's skills folder.
</details>

**Requires Python 3** (standard library only — nothing to `pip install`).

---

## 💬 Step 3 — Use it

Just talk to your agent. The first time you ask anything about your bank, it
will walk you through a one-time setup:

1. It asks for your **Client ID** and **Client Secret** (from Step 1) and stores
   them securely.
2. It asks for your **account IBAN** (e.g. `GE..BG...`) — it's on any statement
   or the home screen of your BOG app. It's **not secret**. You can give several.
   *(BOG has no API to list your accounts, so you provide the IBAN once.)*
3. It auto-detects which currencies that account holds, then shows your first
   **balance** — you're set up.

After that, just ask naturally:

```
"What's my balance?"
"Show me last month's transactions."
"How much did I spend on suppliers in May?"
"Anything unusual or duplicated this month?"
"What's the USD rate today?"
"Add my second account GE....."
```

> 💡 Want to try it before you have credentials? It has a sample-data mode:
> `python3 scripts/bog.py --mock balance`

---

## 🏦 Managing multiple accounts

IBANs are stored and reused; you only ever add or remove them on request.

- **Add another:** *"also track account GE....."* (it's merged — existing
  accounts are kept)
- **Remove one:** *"forget account GE....."* (only removed when you ask)
- **List them:** *"what accounts do you have?"*
- **Default behavior:** if you don't name an account, every request covers **all**
  your accounts across **all** their currencies.

---

## 🔐 Security & privacy

- **Your keys never touch a file in this project.** They're stored in:
  - **macOS** → the system **Keychain** (encrypted), service `bog-business-online`
  - **other OS** → `~/.config/bog-banking/credentials.json`, locked to your user (`600`)
- The skill passes the secret to its tool over **stdin**, never the command line.
- **Read-only:** the code only ever calls `GET` (balance/statement/rates) — there
  is no code path that can move money.
- Each user uses **their own** credentials. Nothing is shared or uploaded.
- Remove everything anytime: *"forget my BOG credentials"* (or
  `python3 scripts/bog.py forget-credentials`).

---

## 🛠 Command reference (the agent runs these — you don't have to)

| Command | Purpose |
|---|---|
| `whoami` | Check whether credentials exist and work |
| `save-credentials` | Store Client ID/Secret (JSON on stdin) |
| `forget-credentials` | Delete stored credentials |
| `add-account --iban GE..` | Add an IBAN (kept until removed; never wipes others) |
| `remove-account --iban GE..` | Remove an IBAN (or one currency with `--currency`) |
| `discover` | Detect each stored IBAN's currencies + balances |
| `accounts` | List stored IBANs + their currencies |
| `balance [--account IBAN] [--currency GEL]` | Available + current balance (all by default) |
| `statement [--from --to] [--account] [--currency]` | Transactions for a period (all by default) |
| `today` | Today's intraday activity |
| `rates [--currency USD]` | NBG official + BOG commercial rates |

Add `--mock` to any read command for sample data.

---

## ❓ Troubleshooting

| Message | Meaning | Fix |
|---|---|---|
| Skill doesn't trigger | Skills load at session start | Open a new session, or type `/bog-banking-skill` |
| `no_keys` | First use | Give the agent your Client ID + Client Secret |
| `invalid_credentials` | Wrong keys **or** API access not activated | Re-check keys; ask your BOG banker to enable API access |
| `no_account` | No IBAN stored | Give the agent your account IBAN |

---

## License

MIT — see [LICENSE](LICENSE). Contributions welcome: open an issue or PR.

*Not affiliated with or endorsed by Bank of Georgia. Use at your own risk.*
