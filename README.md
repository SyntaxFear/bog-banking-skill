# bog-banking

A read-only **Agent Skill** that lets an AI coding agent (Claude Code, Codex,
or any tool that supports the `SKILL.md` standard) read your **Bank of Georgia
Business Online** account and help you manage your finances by conversation:
balances, transactions, spending by supplier/category, cash-flow overviews,
reconciliation, duplicate/odd-transaction spotting, and FX rates.

**Read-only by design** — it can never move money, create payments, or sign
anything.

## Install

```bash
git clone https://github.com/SyntaxFear/claude-bog-banking.git
cd claude-bog-banking
bash install.sh
```

This copies the skill into both tools:
- Claude Code → `~/.claude/skills/bog-banking/`
- Codex → `~/.agents/skills/bog-banking/`

(Or copy this folder into your agent's skills directory manually. On Windows,
place it in your tool's skills directory. Any `SKILL.md`-compatible agent works.)

Requires **Python 3** (standard library only — nothing to `pip install`).

## Use it

Just ask your agent, e.g.:
- *"What's my BOG balance?"*
- *"Show me last month's transactions."*
- *"How much did I spend on suppliers in May?"*
- *"Anything unusual or duplicated this month?"*
- *"What's the USD rate today?"*

**First time:** the agent asks you for your **Client ID**, **Client Secret**,
and **account IBAN**, stores them locally, and reuses them after that. If the
stored credentials ever stop working, it tells you and offers to re-enter them.

Get your credentials by registering an app at `bonline.bog.ge/admin/api`
(choose **Client Credentials Flow**), and ask your BOG business banker to
enable API access for it.

> Want to try it before your credentials are ready? It has a sample-data mode:
> `python3 scripts/bog.py --mock balance --all`

## How your credentials are stored

- **macOS:** the system **Keychain** (encrypted), service `bog-business-online`.
- **Other OS:** `~/.config/bog-banking/credentials.json`, locked to your user
  (file mode `600`).
- Either way, credentials live **outside this folder**, so the skill itself
  contains no secrets and is safe to share/publish. The agent passes the secret
  to the tool over stdin, never on the command line.
- Remove stored credentials any time: `python3 scripts/bog.py forget-credentials`.

## What's inside
```
bog-banking/
  SKILL.md              instructions the agent reads (credential flow + commands)
  scripts/bog.py        read-only tool: whoami, balance, statement, today, rates
  reference/endpoints.md the BOG endpoints used
  install.sh            installs into Claude Code + Codex
  LICENSE               MIT
```

## Commands (the agent runs these; you don't have to)
| Command | Returns |
|---|---|
| `whoami` | whether credentials exist and work |
| `save-credentials` | store credentials (JSON on stdin) |
| `forget-credentials` | delete stored credentials |
| `add-account --iban GE..` | add an IBAN (kept until you remove it; adding never wipes others) |
| `remove-account --iban GE..` | remove an IBAN (or one currency with `--currency`) |
| `discover` | probe stored IBANs' currencies and save the ones with balances |
| `accounts` | stored IBAN(s) + their currencies |
| `balance` | available + current balance (all accounts/currencies by default) |
| `statement [--from --to]` | transactions for a period (all accounts by default) |
| `today` | today's activity |
| `rates [--currency USD]` | NBG + commercial rates |

By default every read covers **all** your accounts and currencies; pass
`--account`/`--currency` only to narrow to a specific one.

Requires Python 3 (standard library only — nothing to install).

## License
MIT. Contributions welcome.
