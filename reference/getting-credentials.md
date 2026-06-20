# Getting your BOG API credentials

This skill needs two values from Bank of Georgia — a **Client ID** and a
**Client Secret** — to read your **Business Online** account. They're free with
a BOG **business** account that has Business Internet Banking.

> Some BOG screens label these the **Public Key** (= Client ID) and **Secret
> Key** (= Client Secret). They're the same values.

## Create the key (first time)

1. **Log in** to your Business Bank: **https://bonline.bog.ge/** (use your
   Business Online username and password).
2. Open the API admin page: **https://bonline.bog.ge/admin/api** and click
   **Add new**.
3. Choose the integration type **Client Credentials Flow** — the automatic type
   that authorizes with a Client ID and Client Secret, with no username or
   password.
4. Enter an **API client name** (any name — e.g. your internet-bank user, or
   `Banking Assistant`).
5. Confirm with the **one-time code (OTP)** BOG sends you.
6. BOG then shows your **Client ID** and **Client Secret** — copy both. Keep the
   Client Secret safe.

## Find the keys again later (existing application)

If you already registered an application and just need the keys:

1. Log in to **https://bonline.bog.ge/**.
2. Go to **Payments Manager → Payment methods**.
3. Open **Applications history**, click the **⋮ (3 dots)** next to the relevant
   application → **Payment details**.
4. You'll see the **Public Key** (Client ID) and **Secret Key** (Client Secret);
   reveal the secret with the **👁 eye icon** and a **one-time code**.

## Give them to the agent

Just paste the **Client ID** and **Client Secret** into the chat when the agent
asks. You do **not** put them in any file — the agent saves them in your OS
keychain (macOS) or a private `0600` file (other systems), and passes the secret
over stdin so it never appears on the command line.

The agent will then ask for your **account IBAN** (e.g. `GE..BG...`) — that's
on any statement or your BOG app home screen, and it's **not secret**. That's
all the setup the skill needs.

## If the keys are rejected (`invalid_credentials`)

Two possible causes:
- **Wrong keys** — double-check you copied the Client ID and Client Secret
  exactly (re-reveal the secret if unsure).
- **API access not activated** — on some accounts, API integration must be
  switched on by your **BOG business banker** before the keys work. Ask them to
  enable API access for your application, then try again.

You can re-enter the keys anytime — just ask the agent, or run
`python3 scripts/bog.py forget-credentials` and start over.

## Try it before your keys are ready

The skill has a sample-data mode that needs no bank access:
```
python3 scripts/bog.py --mock balance
```
Results are clearly fake — useful to see what the skill does before you set up.
