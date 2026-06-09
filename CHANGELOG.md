# Changelog

All notable changes to this project are documented here.
This project follows [Semantic Versioning](https://semver.org/).

## [1.0.0] — 2026-06-09

First production release.

### Features
- Read-only **Bank of Georgia Business Online** access as a cross-agent
  **Agent Skill** (`SKILL.md`) — works in Claude Code, Codex, and any
  `SKILL.md`-compatible agent.
- Conversational setup: the agent asks for the user's **Client ID / Client
  Secret**, then collects **account IBANs one at a time** (BOG has no
  account-list endpoint), auto-detecting each IBAN's currencies.
- Capabilities: **balance**, **statement** (V2, auto-paginated), **today's
  activity**, **exchange rates** (NBG + commercial), across **all accounts and
  currencies** by default.
- Persistent multi-account support: `add-account` (merges, never overwrites),
  `remove-account`, `accounts`, `discover`.
- **One-line install** (`curl … | bash`), pinnable via `BOG_SKILL_REF`.

### Security
- Credentials stored in the **macOS Keychain** or a `0600` file (created
  atomically in a `0700` dir) — never in the repo, never in `ps`/argv/logs.
- Credentials/tokens sent **only over HTTPS** to allowlisted BOG hosts
  (`*.bog.ge`, `*.businessonline.ge`); authenticated calls **do not follow
  redirects**.
- Strict IBAN / currency / date validation prevents URL injection.
- Independently audited (multi-agent adversarial review) — no credential-leak
  findings.

[1.0.0]: https://github.com/SyntaxFear/claude-bog-banking/releases/tag/v1.0.0
