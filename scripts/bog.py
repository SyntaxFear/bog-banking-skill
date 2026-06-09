#!/usr/bin/env python3
"""
bog.py — read-only Bank of Georgia (Business Online) access for AI agents.

The AGENT drives setup conversationally — there is no separate CLI login:
  1) `whoami`                  -> check whether credentials exist and work
  2) if missing/invalid, the agent asks the user for credentials, then:
     `save-credentials`        <- JSON on stdin: {client_id, client_secret, accounts}
  3) then run read-only commands: balance / statement / today / rates

Credentials are stored locally, per user:
  - macOS : the login Keychain (service 'bog-business-online')
  - other : ~/.config/bog-banking/credentials.json  (file mode 0600)
Account IBANs + token URL (not secret) live in ~/.config/bog-banking/config.json.

Read-only: only GET endpoints + login are ever called. It cannot move money.
"""

import argparse
import base64
import json
import os
import re
import select
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

# --------------------------------------------------------------------------
# Locations / constants
# --------------------------------------------------------------------------
__version__ = "1.0.0"

KEYCHAIN_SERVICE = "bog-business-online"
CONFIG_DIR = os.path.expanduser("~/.config/bog-banking")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")        # non-secret
CREDS_FILE = os.path.join(CONFIG_DIR, "credentials.json")    # secret (non-mac)

API_BASE = "https://api.businessonline.ge/api"
DEFAULT_TOKEN_URL = (
    "https://account.bog.ge/auth/realms/bog/protocol/openid-connect/token"
)
MAX_STATEMENT_PAGES = 50
# BOG has no "list accounts" endpoint, but an IBAN is usually multi-currency.
# Given an IBAN we probe these to auto-discover which currencies it holds.
DISCOVER_CURRENCIES = ["GEL", "USD", "EUR", "GBP"]

# Credentials/tokens are ONLY ever sent to these BOG hosts, and only over HTTPS.
ALLOWED_HOST_SUFFIXES = (".bog.ge", ".businessonline.ge")
ALLOWED_HOSTS_EXACT = ("bog.ge", "businessonline.ge")

# Strict shapes so user/server-supplied values can't be injected into URLs.
_IBAN_RE = re.compile(r"^[A-Z0-9]{15,34}$")
_CCY_RE = re.compile(r"^[A-Z]{3}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

IS_MAC = sys.platform == "darwin" and shutil.which("security") is not None

# Authenticated calls must NOT follow redirects (a 3xx could forward the
# Authorization header to another host). Treat any redirect as an error.
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

_OPENER = urllib.request.build_opener(_NoRedirect)


def emit(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _norm_iban(s):
    return re.sub(r"\s+", "", (s or "")).upper()


def _check_secret_url(url, what):
    """Allow sending secrets/tokens ONLY to https BOG hosts. Raises otherwise."""
    parsed = urllib.parse.urlparse(url or "")
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https":
        raise BogError("insecure_url", f"Refusing to send {what} over non-HTTPS.")
    if host not in ALLOWED_HOSTS_EXACT and not host.endswith(ALLOWED_HOST_SUFFIXES):
        raise BogError("untrusted_host",
                       f"Refusing to send {what} to non-BOG host '{host}'.")


# --------------------------------------------------------------------------
# Credential storage  (Keychain on macOS, 0600 file elsewhere)
# --------------------------------------------------------------------------
def _keychain_get(account):
    try:
        r = subprocess.run(
            ["security", "find-generic-password",
             "-s", KEYCHAIN_SERVICE, "-a", account, "-w"],
            capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return ""


def _keychain_set(account, value):
    """Store via a pty so the secret never appears in the process arguments
    and the call works even inside an interactive Terminal."""
    import pty
    master, slave = pty.openpty()
    try:
        proc = subprocess.Popen(
            ["security", "add-generic-password", "-U",
             "-s", KEYCHAIN_SERVICE, "-a", account, "-w"],
            stdin=slave, stdout=slave, stderr=slave, close_fds=True)
        os.close(slave)
        os.write(master, (value + "\n" + value + "\n").encode())
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            return False
        return proc.returncode == 0
    finally:
        try:
            os.close(master)
        except OSError:
            pass


def _keychain_del(account):
    subprocess.run(["security", "delete-generic-password",
                    "-s", KEYCHAIN_SERVICE, "-a", account],
                   capture_output=True, text=True)


def _file_creds_read():
    if os.path.exists(CREDS_FILE):
        try:
            with open(CREDS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def load_secret_creds():
    """Return (client_id, client_secret) from the right backend."""
    if IS_MAC:
        return _keychain_get("CLIENT_ID"), _keychain_get("CLIENT_SECRET")
    d = _file_creds_read()
    return d.get("client_id", ""), d.get("client_secret", "")


def save_secret_creds(cid, secret):
    if IS_MAC:
        return _keychain_set("CLIENT_ID", cid) and _keychain_set("CLIENT_SECRET", secret)
    # Non-macOS file backend: create with 0600 from the start (no world-readable
    # window), in a 0700 dir, and swap in atomically.
    os.makedirs(CONFIG_DIR, mode=0o700, exist_ok=True)
    try:
        os.chmod(CONFIG_DIR, 0o700)
    except OSError:
        pass
    tmp = CREDS_FILE + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"client_id": cid, "client_secret": secret}, f)
    os.replace(tmp, CREDS_FILE)  # atomic; keeps 0600
    return True


def forget_secret_creds():
    if IS_MAC:
        _keychain_del("CLIENT_ID")
        _keychain_del("CLIENT_SECRET")
    elif os.path.exists(CREDS_FILE):
        os.remove(CREDS_FILE)


def have_keys():
    cid, secret = load_secret_creds()
    return bool(cid) and bool(secret)


# --------------------------------------------------------------------------
# Non-secret config (accounts, token url)
# --------------------------------------------------------------------------
def load_config():
    cfg = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
    cfg.setdefault("token_url", DEFAULT_TOKEN_URL)
    cfg.setdefault("api_base", API_BASE)
    cfg.setdefault("accounts", [])
    return cfg


def save_config(cfg):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def resolve_mode(args):
    if getattr(args, "mock", False):
        return "mock"
    if os.environ.get("BOG_MOCK", "").lower() in ("1", "true", "yes"):
        return "mock"
    return "live"


# --- persistent account model -------------------------------------------
# cfg["accounts"] = [ {"iban": "...", "label": "...", "currencies": ["GEL",..]} ]
# IBANs persist until the user removes them. Adding MERGES (never overwrites).
def _find_account(cfg, iban):
    for a in cfg.get("accounts", []):
        if a.get("iban") == iban:
            return a
    return None


def _entry_currencies(entry):
    """Currencies stored on an entry (tolerates the older {iban,currency} shape)."""
    if entry.get("currencies"):
        return list(entry["currencies"])
    if entry.get("currency"):
        return [entry["currency"]]
    return []


def add_accounts(cfg, items):
    """Merge IBAN(s) into cfg['accounts'] WITHOUT dropping existing ones.
    Each item is {iban, currency?, label?} (or a bare iban string).
    Dedupes by IBAN; merges any provided currency into that IBAN. Returns the
    list of newly-added IBANs."""
    accounts = cfg.setdefault("accounts", [])
    added = []
    for it in items:
        iban = _norm_iban(it.get("iban") if isinstance(it, dict) else it)
        if not _IBAN_RE.match(iban):
            continue  # skip anything that isn't a plausible IBAN (15-34 [A-Z0-9])
        entry = _find_account(cfg, iban)
        if entry is None:
            entry = {"iban": iban, "label": "", "currencies": []}
            accounts.append(entry)
            added.append(iban)
        entry.setdefault("currencies", [])
        if isinstance(it, dict):
            cur = (it.get("currency") or "").strip().upper()
            if cur and _CCY_RE.match(cur) and cur not in entry["currencies"]:
                entry["currencies"].append(cur)
            if it.get("label") and not entry.get("label"):
                entry["label"] = str(it["label"]).strip()
    return added


def remove_account(cfg, iban, currency=None):
    """Remove an IBAN (or just one currency from it). Returns True if found."""
    entry = _find_account(cfg, iban)
    if not entry:
        return False
    if currency:
        cur = currency.strip().upper()
        entry["currencies"] = [c for c in entry.get("currencies", []) if c != cur]
    else:
        cfg["accounts"] = [a for a in cfg.get("accounts", []) if a.get("iban") != iban]
    return True


def probe_currencies(cfg, iban, token):
    """Find which common currencies an IBAN holds by checking each balance."""
    found = []
    for ccy in DISCOVER_CURRENCIES:
        try:
            bal = api_get(cfg, token, f"accounts/{iban}/{ccy}")
        except BogError:
            continue
        if isinstance(bal, dict) and ("AvailableBalance" in bal or "CurrentBalance" in bal):
            found.append(ccy)
    return found


def resolve_targets(args, cfg, token):
    """Return the (iban, currency) pairs to operate on.

    Defaults to EVERYTHING — every stored IBAN across every currency it holds —
    unless the user is specific via --account and/or --currency. IBAN/currency
    are optional for the user but always resolved here for the API."""
    acc = _norm_iban(getattr(args, "account", None)) if getattr(args, "account", None) else None
    ccy = getattr(args, "currency", None)
    if acc and not _IBAN_RE.match(acc):
        raise BogError("bad_iban", f"'{acc}' is not a valid IBAN (15-34 letters/digits).")
    if ccy and not _CCY_RE.match(ccy.upper()):
        raise BogError("bad_currency", f"'{ccy}' is not a valid 3-letter currency code.")
    if acc:
        entries = [_find_account(cfg, acc) or {"iban": acc, "currencies": []}]
    else:
        entries = list(cfg.get("accounts", []))
    if not entries:
        raise BogError("no_account",
                       "No IBAN stored. Ask the user for at least one account IBAN.")
    targets = []
    for entry in entries:
        iban = entry.get("iban")
        if not iban or not _IBAN_RE.match(iban):
            continue  # never let a malformed stored IBAN reach a URL
        curs = [ccy.upper()] if ccy else (_entry_currencies(entry) or probe_currencies(cfg, iban, token))
        for c in curs:
            if _CCY_RE.match(c or "") and (iban, c) not in targets:
                targets.append((iban, c))
    if not targets:
        raise BogError("no_currency",
                       "Could not determine any currency for the account(s). "
                       "Run `discover`, or pass --currency.")
    return targets


# --------------------------------------------------------------------------
# Live BOG access (read-only)
# --------------------------------------------------------------------------
class BogError(Exception):
    def __init__(self, code, message, detail=""):
        super().__init__(message)
        self.code, self.message, self.detail = code, message, detail


def get_token(cfg):
    cid, secret = load_secret_creds()
    if not cid or not secret:
        raise BogError("no_keys",
                       "No credentials stored yet. Ask the user for their BOG "
                       "Client ID and Client Secret, then save them.")
    _check_secret_url(cfg.get("token_url", ""), "credentials")
    body = urllib.parse.urlencode(
        {"grant_type": "client_credentials", "scope": "corp"}).encode()
    auth = base64.b64encode(f"{cid}:{secret}".encode()).decode()
    req = urllib.request.Request(cfg["token_url"], data=body, method="POST")
    req.add_header("Authorization", "Basic " + auth)
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with _OPENER.open(req, timeout=25) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
        token = data.get("access_token")
        if not token:
            raise BogError("no_token", "Login returned no access token.")
        return token
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        if e.code in (400, 401, 403):
            raise BogError(
                "invalid_credentials",
                "BOG rejected these credentials. Either the Client ID/Secret "
                "is wrong, or API access has not been activated yet by the "
                "user's BOG business banker. Ask the user to double-check the "
                "keys and/or confirm activation, then offer to re-enter them.",
                detail)
        raise BogError("login_http_error", f"Login failed (HTTP {e.code}).", detail)
    except urllib.error.URLError as e:
        raise BogError("network", f"Could not reach BOG: {e.reason}")


def api_get(cfg, token, path):
    url = cfg["api_base"].rstrip("/") + "/" + path.lstrip("/")
    _check_secret_url(url, "the access token")
    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Accept", "application/json")
    try:
        with _OPENER.open(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", "replace")
        return json.loads(raw) if raw.strip() else None
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise BogError("api_http_error", f"Request failed (HTTP {e.code}) for {path}.", detail)
    except urllib.error.URLError as e:
        raise BogError("network", f"Could not reach BOG: {e.reason}")


# --------------------------------------------------------------------------
# Sample data (mock mode, for trying the skill before access is live)
# --------------------------------------------------------------------------
MOCK_ACCOUNTS = [
    {"iban": "GE00BG0000000SAMPLE01", "currency": "GEL", "label": "Main (GEL)"},
    {"iban": "GE00BG0000000SAMPLE02", "currency": "USD", "label": "USD account"},
]
MOCK_TXNS = [
    ("2026-05-04", 0, 8200.00, "ACME Trading LLC", "Invoice INV-2041 payment", "income"),
    ("2026-05-06", 1450.00, 0, "Silknet JSC", "Internet & telecom May", "utilities"),
    ("2026-05-09", 320.50, 0, "Wissol Petroleum", "Fuel", "transport"),
    ("2026-05-12", 5400.00, 0, "Office Supplies Geo", "Furniture purchase", "supplies"),
    ("2026-05-15", 12000.00, 0, "Payroll batch", "Salaries May (8 staff)", "payroll"),
    ("2026-05-15", 980.00, 0, "Telasi", "Electricity", "utilities"),
    ("2026-05-18", 0, 3100.00, "Beta Solutions", "Consulting fee", "income"),
    ("2026-05-20", 5400.00, 0, "Office Supplies Geo", "Furniture purchase", "supplies"),
    ("2026-05-22", 210.00, 0, "Bank fee", "Monthly service fee", "fees"),
    ("2026-05-25", 1450.00, 0, "Silknet JSC", "Internet & telecom (retry?)", "utilities"),
    ("2026-05-28", 7600.00, 0, "Global Imports Ltd", "Supplier payment PO-557", "suppliers"),
    ("2026-05-30", 0, 15250.00, "ACME Trading LLC", "Invoice INV-2052 payment", "income"),
]


def mock_balance(iban, currency):
    return {"AvailableBalance": 18430.75, "CurrentBalance": 18430.75,
            "iban": iban, "currency": currency}


def mock_records(frm, to, currency):
    out = []
    for d, debit, credit, who, nom, cat in MOCK_TXNS:
        if (frm and d < frm) or (to and d > to):
            continue
        out.append({"EntryDate": d, "EntryAmountDebit": debit,
                    "EntryAmountCredit": credit, "Counterparty": who,
                    "DocumentNomination": nom, "CategoryHint": cat,
                    "Currency": currency})
    return out


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------
def cmd_whoami(args, cfg, mode):
    if mode == "mock":
        return {"command": "whoami", "mode": mode, "ok": True,
                "data": {"credentials_present": have_keys(),
                         "accounts_configured": len(cfg.get("accounts", []))},
                "note": "MOCK mode (sample data)."}
    if not have_keys():
        return {"command": "whoami", "mode": "live", "ok": False,
                "error": "no_keys",
                "message": "No credentials stored. Ask the user for their BOG "
                           "Client ID and Client Secret, then run save-credentials."}
    token = get_token(cfg)  # raises invalid_credentials if rejected
    return {"command": "whoami", "mode": "live", "ok": True,
            "data": {"login": "success",
                     "accounts_configured": len(cfg.get("accounts", []))},
            "note": "Credentials valid — connected to BOG."}


def cmd_save_credentials(args, cfg, mode):
    raw = _read_stdin_raw()
    try:
        data = json.loads(raw)
    except Exception:
        return {"command": "save-credentials", "ok": False, "error": "bad_json",
                "message": "Pipe a JSON object on stdin: "
                           '{"client_id":"...","client_secret":"...",'
                           '"accounts":[{"iban":"...","currency":"GEL"}]}'}
    cid = (data.get("client_id") or "").strip()
    secret = (data.get("client_secret") or "").strip()
    has_accounts = isinstance(data.get("accounts"), list)
    if not cid and not secret and not has_accounts and not data.get("token_url"):
        return {"command": "save-credentials", "ok": False, "error": "missing",
                "message": "Provide client_id + client_secret, and/or an accounts list."}
    keys_ok = True
    if cid or secret:
        if not cid or not secret:
            return {"command": "save-credentials", "ok": False, "error": "missing",
                    "message": "client_id and client_secret must be provided together."}
        keys_ok = save_secret_creds(cid, secret)
    if has_accounts:
        add_accounts(cfg, data["accounts"])  # merge, never overwrite
    if data.get("token_url"):
        cfg["token_url"] = data["token_url"]
    save_config(cfg)
    return {"command": "save-credentials", "ok": bool(keys_ok),
            "data": {"keys_stored": bool(cid and secret and keys_ok),
                     "backend": "keychain" if IS_MAC else "file",
                     "accounts_configured": len(cfg.get("accounts", []))},
            "note": "Saved." if keys_ok else "Failed to store credentials."}


def cmd_forget_credentials(args, cfg, mode):
    forget_secret_creds()
    return {"command": "forget-credentials", "ok": True,
            "note": "Stored credentials removed."}


def _read_stdin_raw():
    """Read piped stdin if any; return '' immediately if nothing is piped.
    Uses select so it NEVER blocks when stdin has no data (e.g. flag-only call)."""
    try:
        if sys.stdin.isatty():
            return ""
        r, _, _ = select.select([sys.stdin], [], [], 0.3)
        if not r:
            return ""
        return sys.stdin.read()
    except Exception:
        return ""


def _stdin_items():
    """Accounts from piped stdin JSON, if any. Returns a list (maybe empty)."""
    raw = _read_stdin_raw().strip()
    if not raw:
        return []
    data = json.loads(raw)
    if isinstance(data, dict) and isinstance(data.get("accounts"), list):
        return data["accounts"]
    if isinstance(data, list):
        return data
    return []


def cmd_add_account(args, cfg, mode):
    """Add one or more IBANs (merged into the stored list; existing ones kept)."""
    items = []
    if getattr(args, "iban", None):
        items.append({"iban": args.iban,
                      "currency": getattr(args, "currency", None),
                      "label": getattr(args, "label", None)})
    else:
        try:
            items = _stdin_items()
        except Exception:
            return {"command": "add-account", "ok": False, "error": "bad_json",
                    "message": 'Pipe {"accounts":[{"iban":"GE.."}]} or use --iban GE..'}
    items = [it for it in items if (it.get("iban") if isinstance(it, dict) else it)]
    if not items:
        return {"command": "add-account", "ok": False, "error": "missing",
                "message": "Provide --iban GE.. or pipe an accounts list."}
    # reject obviously malformed IBANs up front with a clear message
    bad = [_norm_iban(it.get("iban") if isinstance(it, dict) else it) for it in items]
    bad = [b for b in bad if not _IBAN_RE.match(b)]
    if bad and len(bad) == len(items):
        return {"command": "add-account", "ok": False, "error": "bad_iban",
                "message": f"Not a valid IBAN: {', '.join(bad)} (expected 15-34 letters/digits)."}
    added = add_accounts(cfg, items)
    save_config(cfg)
    return {"command": "add-account", "mode": mode, "ok": True,
            "data": {"added": added, "accounts": cfg.get("accounts", [])},
            "note": (f"Added {len(added)} new IBAN(s); run `discover` to detect currencies."
                     if added else "IBAN already stored — nothing new added.")}


def cmd_remove_account(args, cfg, mode):
    """Remove an IBAN (or just one currency from it) — only on explicit request."""
    iban = _norm_iban(getattr(args, "iban", None)) if getattr(args, "iban", None) else None
    if not iban:
        return {"command": "remove-account", "ok": False, "error": "missing",
                "message": "Provide --iban GE.. (optionally --currency to drop one currency)."}
    ok = remove_account(cfg, iban, getattr(args, "currency", None))
    save_config(cfg)
    return {"command": "remove-account", "mode": mode, "ok": bool(ok),
            "data": {"accounts": cfg.get("accounts", [])},
            "note": ("Removed." if ok else "That IBAN was not in the stored list.")}


def cmd_accounts(args, cfg, mode):
    accounts = MOCK_ACCOUNTS if mode == "mock" else cfg.get("accounts", [])
    note = None
    if mode == "live" and not accounts:
        note = "No accounts configured. Ask the user for their IBAN + currency."
    return {"command": "accounts", "mode": mode, "ok": True, "data": accounts, "note": note}


def _mock_targets(args):
    """In mock mode, pick the sample accounts to act on (all, unless narrowed)."""
    accts = MOCK_ACCOUNTS
    acc = getattr(args, "account", None)
    if acc:
        accts = [a for a in MOCK_ACCOUNTS if a["iban"] == acc] or \
                [{"iban": acc, "currency": (getattr(args, "currency", None) or "GEL")}]
    ccy = getattr(args, "currency", None)
    if ccy:
        accts = [{**a, "currency": ccy.upper()} for a in accts]
    return accts


def cmd_balance(args, cfg, mode):
    if mode == "mock":
        return {"command": "balance", "mode": mode, "ok": True,
                "data": [mock_balance(a["iban"], a["currency"]) for a in _mock_targets(args)]}
    token = get_token(cfg)
    data = []
    for iban, ccy in resolve_targets(args, cfg, token):
        try:
            bal = api_get(cfg, token, f"accounts/{iban}/{ccy}")
            data.append({**(bal or {}), "iban": iban, "currency": ccy})
        except BogError as e:
            data.append({"iban": iban, "currency": ccy, "error": e.code, "message": e.message})
    return {"command": "balance", "mode": mode, "ok": True, "data": data}


def cmd_statement(args, cfg, mode):
    to = args.to or date.today().isoformat()
    frm = getattr(args, "from_date", None) or (date.today() - timedelta(days=30)).isoformat()
    if not _DATE_RE.match(frm) or not _DATE_RE.match(to):
        return {"command": "statement", "mode": mode, "ok": False, "error": "bad_date",
                "message": "Dates must be in YYYY-MM-DD format."}
    if mode == "mock":
        out = [{"iban": a["iban"], "currency": a["currency"], "from": frm, "to": to,
                "Records": (mock_records(frm, to, a["currency"]) if a["currency"] == "GEL" else [])}
               for a in _mock_targets(args)]
        for o in out:
            o["Count"] = len(o["Records"])
        return {"command": "statement", "mode": mode, "ok": True, "data": out,
                "note": "Sample transactions."}
    token = get_token(cfg)
    out = []
    for iban, ccy in resolve_targets(args, cfg, token):
        try:
            # Statement V2 (V1 is deprecated per BOG's Postman collection).
            gen = api_get(cfg, token, f"statement/v2/{iban}/{ccy}/{frm}/{to}") or {}
            records = list(gen.get("Records") or [])
            stid = gen.get("Id")
            stid = str(stid) if stid is not None and str(stid).isdigit() else None
            total = gen.get("Count") or len(records)
            # V2 pagination: the call above is page 1; extra pages start at 2.
            page = 2
            while stid and len(records) < total and page <= MAX_STATEMENT_PAGES + 1:
                chunk = api_get(cfg, token, f"statement/v2/{iban}/{ccy}/{stid}/{page}")
                items = chunk if isinstance(chunk, list) else (chunk or {}).get("Records") or []
                if not items:
                    break
                records.extend(items)
                page += 1
            out.append({"iban": iban, "currency": ccy, "from": frm, "to": to,
                        "Count": len(records), "Records": records})
        except BogError as e:
            out.append({"iban": iban, "currency": ccy, "error": e.code, "message": e.message})
    return {"command": "statement", "mode": mode, "ok": True, "data": out}


def cmd_today(args, cfg, mode):
    if mode == "mock":
        out = [{"iban": a["iban"], "currency": a["currency"], "date": date.today().isoformat(),
                "Records": (mock_records(None, None, a["currency"])[:3] if a["currency"] == "GEL" else [])}
               for a in _mock_targets(args)]
        return {"command": "today", "mode": mode, "ok": True, "data": out,
                "note": "Sample intraday activity."}
    token = get_token(cfg)
    out = []
    for iban, ccy in resolve_targets(args, cfg, token):
        try:
            out.append({"iban": iban, "currency": ccy,
                        "activities": api_get(cfg, token, f"documents/todayactivities/{iban}/{ccy}")})
        except BogError as e:
            out.append({"iban": iban, "currency": ccy, "error": e.code, "message": e.message})
    return {"command": "today", "mode": mode, "ok": True, "data": out}


def cmd_rates(args, cfg, mode):
    cur = (getattr(args, "currency", None) or "USD").upper()
    if not _CCY_RE.match(cur):
        return {"command": "rates", "mode": mode, "ok": False, "error": "bad_currency",
                "message": "Currency must be a 3-letter code (e.g. USD)."}
    if mode == "mock":
        return {"command": "rates", "mode": mode, "ok": True,
                "data": {"currency": cur, "nbg": 2.71,
                         "commercial": {"Buy": 2.69, "Sell": 2.74}},
                "note": "Sample rates."}
    token = get_token(cfg)
    return {"command": "rates", "mode": mode, "ok": True,
            "data": {"currency": cur,
                     "nbg": api_get(cfg, token, f"rates/nbg/{cur}"),
                     "commercial": api_get(cfg, token, f"rates/commercial/{cur}")}}


def cmd_discover(args, cfg, mode):
    """Detect each stored IBAN's currencies (and current balances) and save them.

    BOG has NO account-list endpoint (verified live), so IBANs only ever come
    from the user via add-account. This just probes which currencies an IBAN
    holds — it never tries to auto-discover account numbers."""
    if mode == "mock":
        found = [{**a, **mock_balance(a["iban"], a["currency"])} for a in MOCK_ACCOUNTS]
        return {"command": "discover", "mode": mode, "ok": True, "data": found,
                "note": "Sample: detected currencies."}

    token = get_token(cfg)
    acc = _norm_iban(args.account) if getattr(args, "account", None) else None
    if acc:
        if not _IBAN_RE.match(acc):
            raise BogError("bad_iban", f"'{acc}' is not a valid IBAN (15-34 letters/digits).")
        add_accounts(cfg, [{"iban": acc}])

    entries = ([_find_account(cfg, acc)] if acc else list(cfg.get("accounts", [])))
    entries = [e for e in entries if e and e.get("iban") and _IBAN_RE.match(e["iban"])]
    if not entries:
        raise BogError("no_account",
                       "No IBAN stored. Ask the user for an account IBAN (add-account).")

    override = getattr(args, "currencies", None)
    probe_list = ([c for c in (s.strip().upper() for s in override.split(","))
                   if _CCY_RE.match(c)] if override else DISCOVER_CURRENCIES) or DISCOVER_CURRENCIES
    found = []
    for entry in entries:
        iban = entry["iban"]
        cur_found = []
        for ccy in probe_list:
            try:
                bal = api_get(cfg, token, f"accounts/{iban}/{ccy}")
            except BogError:
                continue
            if isinstance(bal, dict) and ("AvailableBalance" in bal or "CurrentBalance" in bal):
                cur_found.append(ccy)
                found.append({"iban": iban, "currency": ccy,
                              "AvailableBalance": bal.get("AvailableBalance"),
                              "CurrentBalance": bal.get("CurrentBalance")})
        if cur_found:
            entry["currencies"] = cur_found   # refresh; entry kept regardless
    save_config(cfg)                          # persist (keeps all stored IBANs)
    return {"command": "discover", "mode": mode, "ok": True, "data": found,
            "note": (f"Detected currencies for {len(entries)} account(s); {len(found)} balance(s)."
                     if found else "No balances found — double-check the IBAN.")}


def cmd_version(args, cfg, mode):
    return {"command": "version", "ok": True, "data": {"version": __version__}}


COMMANDS = {
    "version": cmd_version,
    "whoami": cmd_whoami,
    "save-credentials": cmd_save_credentials,
    "forget-credentials": cmd_forget_credentials,
    "add-account": cmd_add_account,
    "remove-account": cmd_remove_account,
    "discover": cmd_discover,
    "accounts": cmd_accounts,
    "balance": cmd_balance,
    "statement": cmd_statement,
    "today": cmd_today,
    "rates": cmd_rates,
}


def build_parser():
    p = argparse.ArgumentParser(description="Read-only BOG Business Online access.")
    p.add_argument("--mock", action="store_true", help="Use sample data.")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("version", help="Print the skill version.")
    sub.add_parser("whoami", help="Check whether credentials exist and work.")
    sub.add_parser("save-credentials", help="Store credentials (JSON on stdin).")
    sub.add_parser("forget-credentials", help="Delete stored credentials.")
    aa = sub.add_parser("add-account", help="Add IBAN(s) (merged, kept until removed).")
    aa.add_argument("--iban"); aa.add_argument("--currency"); aa.add_argument("--label")
    ra = sub.add_parser("remove-account", help="Remove an IBAN (or one currency).")
    ra.add_argument("--iban"); ra.add_argument("--currency")
    dsc = sub.add_parser("discover", help="Probe stored IBANs' currencies + save them.")
    dsc.add_argument("--account"); dsc.add_argument("--currencies")
    sub.add_parser("accounts", help="List stored accounts + their currencies.")
    b = sub.add_parser("balance"); b.add_argument("--account"); b.add_argument("--currency"); b.add_argument("--all", action="store_true")
    s = sub.add_parser("statement"); s.add_argument("--account"); s.add_argument("--currency"); s.add_argument("--from", dest="from_date"); s.add_argument("--to")
    t = sub.add_parser("today"); t.add_argument("--account"); t.add_argument("--currency")
    r = sub.add_parser("rates"); r.add_argument("--currency")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    cfg = load_config()
    mode = resolve_mode(args)
    try:
        emit(COMMANDS[args.command](args, cfg, mode))
        return 0
    except BogError as e:
        emit({"command": args.command, "mode": mode, "ok": False,
              "error": e.code, "message": e.message, "detail": e.detail})
        return 1
    except Exception as e:  # noqa: BLE001
        emit({"command": args.command, "mode": mode, "ok": False,
              "error": "unexpected", "message": str(e)})
        return 1


if __name__ == "__main__":
    sys.exit(main())
