# BOG Business Online — endpoints used by this skill (read-only)

Base URL: `https://api.businessonline.ge/api`
Auth: OAuth 2.0 client_credentials → JWT bearer. Token endpoint:
`https://account.bog.ge/auth/realms/bog/protocol/openid-connect/token`
(scope `corp`, Basic auth with client_id:client_secret). Keys live in the
macOS Keychain (service `bog-business-online`) on macOS, or in a 0600 file at
`~/.config/bog-banking/credentials.json` on other platforms.

All endpoints below are **GET** (read-only). The skill never calls any
write/payment endpoint.

| Purpose | Method | Path | Notes |
|---|---|---|---|
| Available + current balance | GET | `accounts/{iban}/{currency}` | Returns `AvailableBalance`, `CurrentBalance` |
| Generate statement (V2) | GET | `statement/v2/{iban}/{currency}/{from}/{to}` | Returns `Id`, `Count`, `Records[]` (rich Sender/BeneficiaryDetails); ≤1000 rows. V1 `statement/...` is DEPRECATED. |
| Statement page (V2) | GET | `statement/v2/{iban}/{currency}/{id}/{page}` | For >1000 rows; **pages start at 2** (page 1 = the generate call); tool auto-paginates |
| Today's activity | GET | `documents/todayactivities/{iban}/{currency}` | Intraday entries |
| NBG official rate | GET | `rates/nbg/{currency}` | Single decimal vs GEL |
| BOG commercial rate | GET | `rates/commercial/{currency}` | `{ Buy, Sell }` |

Dates are `YYYY-MM-DD`. Currencies are ISO 4217 (`GEL`, `USD`, `EUR`, `GBP`).

## Not in this skill (deliberately)
- No payment/transfer creation (`documents/*` POST), no signing, no cancellation.
- Statements expose only the first ~1000 rows per page; the tool pages through
  them up to a safety cap (50 pages ≈ 50,000 rows).

## Future (Phase 2, not built)
Drafting payments: the agent would create a transfer document via the API,
which appears in BOG as **"to be signed"**; the user signs it in their BOG
web/mobile bank. The agent would never finalize money on its own.
