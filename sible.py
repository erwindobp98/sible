"""
Sible Mining Runner — IMAP Edition
"""

import asyncio
import base64
import csv
import email
import imaplib
import json
import os
import random
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from email.header import decode_header
from email.utils import parsedate_to_datetime
from typing import Optional

import httpx
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.console import Group
from rich.text import Text

# ═══════════════════════════════════════════════════════════
#  CONSTANTS
# ═══════════════════════════════════════════════════════════
BASE = "https://prod.sible.network/api/v1"
ORIGIN = "https://mine.sible.network"

# ─── FRESH EMAIL THRESHOLD ───
FRESH_AGE_SEC = 60          # email < 60 detik = fresh → stop scan
EARLY_RETURN = True         # kalau False, scan semua

UAS = [
    "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 12; Pixel 6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.144 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 11; Redmi Note 9S) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/120.0.6099.119 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; SM-A546B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; Infinix X6819) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Mobile Safari/537.36",
]

LANGS = [
    "en-GB,en;q=0.9", "en-US,en;q=0.9", "en-GB,en;q=0.9,fr;q=0.8",
    "fr-FR,fr;q=0.9,en;q=0.8", "ar-MA,ar;q=0.9,fr;q=0.8,en;q=0.7", "ar-SA,ar;q=0.9,en;q=0.8",
]

CH_VERSIONS = [str(v) for v in range(118, 141)]
CH_PLATFORMS = ['"Android"', '"Android"', '"Android"', '"iOS"', '"Windows"', '"macOS"']


def rnd(arr): return random.choice(arr)
def rand_int(a, b): return random.randint(a, b)
def sleep_sec(s): return asyncio.sleep(s)
def fmt(n): return f"{n:.8f}" if isinstance(n, (int, float)) else str(n)


def random_ua():
    return rnd(UAS)


def random_sec_ua(ua):
    major = rnd(CH_VERSIONS)
    mobile = "?1" if re.search(r"Mobile|Android|iPhone", ua or "", re.I) else "?0"
    return {
        "sec-ch-ua": f'"Chromium";v="{major}", "Not?A_Brand";v="24"',
        "sec-ch-ua-mobile": mobile,
        "sec-ch-ua-platform": rnd(CH_PLATFORMS),
    }


# ═══════════════════════════════════════════════════════════
#  CLI FLAGS
# ═══════════════════════════════════════════════════════════
def parse_argv():
    args = sys.argv[1:]
    def flag(name, default=None):
        prefix = f"--{name}="
        for a in args:
            if a.startswith(prefix):
                return a[len(prefix):]
        return default
    def has(name):
        return f"--{name}" in args
    return {
        "file": flag("file", "accounts-auth.json"),
        "config": flag("config", "config.json"),
        "accounts": flag("accounts", "accounts.json"),
        "only": flag("only"), "exclude": flag("exclude"),
        "interval": flag("interval"),
        "once": has("once"), "loop": has("loop"),
        "quiet": has("quiet"), "debug_refresh": has("debug-refresh"),
    }


ARGV = parse_argv()
AUTH_FILE = ARGV["file"]
CONFIG_FILE = ARGV["config"]
ACCOUNTS_FILE = ARGV["accounts"]
ONLY = ARGV["only"]
EXCLUDE = ARGV["exclude"]


# ═══════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════
DEFAULTS = {
    "referralCode": "ween", "interval": 28920, "jitterSec": 3,
    "minDelayBetweenAccountsSec": 2, "maxDelayBetweenAccountsSec": 6,
    "rateLimitBackoffSec": 30, "refreshEndpoint": "/auth/refresh",
    "autoRelogin": True, "reloginOn401": True, "logCsv": True,
    "csvFile": "mining-log.csv", "discordWebhook": "", "quiet": False,
    "debugRefresh": True,

    # ─── IMAP ───
    "imapHost": "imap.gmail.com",
    "imapPort": 993,
    "otpTimeoutSec": 30,
    "otpPollIntervalSec": 10,
    "otpMaxAgeSec": 300,
    "otpSinceToleranceSec": 270,

    # ─── Early return ───
    "earlyReturnSec": 270,       # ← email < 270 detik → stop scan

    # ─── Retry ───
    "loginMaxRetry": 5,
    "loginRetryDelaySec": 10,
}


def ensure_config():
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULTS, f, indent=4)
        print(f"📝 Generated {CONFIG_FILE} — edit dulu lalu jalankan ulang.")
        sys.exit(0)
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            user = json.load(f)
    except Exception as e:
        print(f"❌ cannot parse {CONFIG_FILE}: {e}")
        sys.exit(1)
    cfg = dict(DEFAULTS)
    cfg.update(user)
    return cfg


CFG = ensure_config()
INTERVAL = int(ARGV["interval"]) * 1000 if ARGV["interval"] else CFG["interval"] * 1000
LOOP = ARGV["loop"] or not ARGV["once"]
QUIET = ARGV["quiet"] or CFG.get("quiet", False)
DEBUG_REFRESH = ARGV["debug_refresh"] or CFG.get("debugRefresh", True)


# ═══════════════════════════════════════════════════════════
#  LOGGER
# ═══════════════════════════════════════════════════════════
_LOG_FILE = None


def init_log():
    global _LOG_FILE
    try:
        os.makedirs("debug", exist_ok=True)
        _LOG_FILE = open("debug/run.log", "a", encoding="utf-8", buffering=1)
        _LOG_FILE.write(f"\n=== SESSION START {datetime.now(timezone.utc).isoformat()} ===\n")
        _LOG_FILE.flush()
    except Exception as e:
        print(f"⚠️ cannot open log: {e}")


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    if _LOG_FILE:
        try:
            _LOG_FILE.write(line + "\n")
            _LOG_FILE.flush()
        except Exception:
            pass


def close_log():
    global _LOG_FILE
    if _LOG_FILE:
        try:
            _LOG_FILE.close()
        except Exception:
            pass
        _LOG_FILE = None


# ═══════════════════════════════════════════════════════════
#  ACCOUNT VIEW
# ═══════════════════════════════════════════════════════════
class AccountView:
    def __init__(self, label, email):
        self.label = label
        self.email = email
        self.username = ""
        self.balance = 0.0
        self.rate = 0.0
        self.ads_watched = 0
        self.ads_max = 3
        self.boost_pct = 0
        self.running = False
        self.cycles = 0
        self.next_wake = 0.0
        self.last_msg = ""
        self.error = ""
        self.status_icon = "⏳"
        self.status_color = "grey50"
        self.status_text = "idle"
        self.status_detail = ""


# ═══════════════════════════════════════════════════════════
#  DASHBOARD
# ═══════════════════════════════════════════════════════════
class Dashboard:
    def __init__(self, console, views):
        self.console = console
        self.views = views
        self.start_time = time.time()
        self._live = None
        self._paused = False
        self.stop = False

    def pause(self):
        if self._live and not self._paused:
            try:
                self._live.stop()
                self._paused = True
                return True
            except Exception:
                pass
        return False

    def resume(self, was_paused):
        if was_paused and self._live:
            try:
                self._live.start()
                self._paused = False
            except Exception:
                pass

    def _build_status_cell(self, v):
        icon = v.status_icon
        color = v.status_color
        text = v.status_text
        detail = v.status_detail
        if detail:
            return f"[{color}]{icon} {text}[/{color}] [grey50]· {detail}[/grey50]"
        return f"[{color}]{icon} {text}[/{color}]"

    def render(self):
        now = time.time()
        panels = []
        for v in self.views:
            lines = []
            status_str = self._build_status_cell(v)
            lines.append(f"[grey50]Status [/grey50]  : {status_str}")
            bal = fmt(v.balance) if v.balance else "-"
            lines.append(f"[grey50]Balance[/grey50]  : [green]{bal}[/green]")
            rate = fmt(v.rate) if v.rate else "-"
            lines.append(f"[grey50]Rate/hr[/grey50]  : [green]{rate}[/green]")
            ads = f"{v.ads_watched}/{v.ads_max}"
            boost = f"+{v.boost_pct}%"
            run = "[green]✓[/green]" if v.running else "[red]✗[/red]"
            lines.append(
                f"[grey50]Ads[/grey50]      : [magenta]{ads}[/magenta]"
                f"   [grey50]Boost[/grey50] : [green]{boost}[/green]"
                f"   [grey50]Run[/grey50] : {run}"
            )
            next_in = ""
            if v.next_wake > now:
                next_in = f"{int(v.next_wake - now)}s"
            elif v.next_wake > 0:
                next_in = "now"
            lines.append(
                f"[grey50]Cycle[/grey50]    : {v.cycles}"
                f"   [grey50]Next[/grey50] : {next_in or '-'}"
            )
            err = v.error or v.last_msg or ""
            if err:
                lines.append(f"[red]{err[:60]}[/red]")
            content = "\n".join(lines)
            title = f"[bold cyan]{v.username or v.label}[/bold cyan]"
            if v.username and v.balance > 0:
                subtitle = "[green]logged in[/green]"
            elif v.status_text in ("login failed", "error"):
                subtitle = "[red]failed[/red]"
            else:
                subtitle = "[yellow]starting[/yellow]"
            panel = Panel(
                content, title=title, subtitle=subtitle,
                title_align="left", subtitle_align="right",
                border_style="grey50", padding=(0, 1),
            )
            panels.append(panel)
        if panels:
            body = Group(*panels)
        else:
            body = Text("(no accounts)", style="grey50")
        return Panel(
            body,
            title="[bold cyan]⛏️  SIBLE MINING[/bold cyan]",
            title_align="left", border_style="cyan", padding=(1, 1),
        )

    async def run(self):
        with Live(self.render(), console=self.console,
                  refresh_per_second=4, screen=True) as live:
            self._live = live
            while not self.stop:
                try:
                    live.update(self.render())
                except Exception:
                    pass
                await asyncio.sleep(0.25)


# ═══════════════════════════════════════════════════════════
#  HELPER
# ═══════════════════════════════════════════════════════════
def set_status(view, icon, color, text, detail=""):
    if not view:
        return
    view.status_icon = icon
    view.status_color = color
    view.status_text = text
    view.status_detail = detail


# ═══════════════════════════════════════════════════════════
#  STORAGE
# ═══════════════════════════════════════════════════════════
def load_store():
    if not os.path.exists(AUTH_FILE):
        return {"createdAt": datetime.now(timezone.utc).isoformat(), "accounts": []}
    try:
        with open(AUTH_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"createdAt": datetime.now(timezone.utc).isoformat(), "accounts": []}


def save_store(data):
    with open(AUTH_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


DEFAULT_ACCOUNTS = {
    "accounts": [
        {
            "label": "akun1",
            "email": "akun1@gmail.com",
            "siblePassword": "PASSWORD_SIBLE_KAMU",
            "gmailAppPassword": "abcdefghijklmnop"
        }
    ]
}


def load_accounts(file):
    if not os.path.exists(file):
        with open(file, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_ACCOUNTS, f, indent=4)
        print(f"📝 Generated {file} — isi akun, lalu jalankan ulang.")
        print(f"   ⚠️ gmailAppPassword = 16 karakter App Password")
        print(f"   ⚠️ Buat di: https://myaccount.google.com/apppasswords")
        sys.exit(0)
    try:
        with open(file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        raise ValueError(f"cannot parse {file}: {e}")

    lst = data if isinstance(data, list) else data.get("accounts", [])
    out = []
    for a in lst:
        if not isinstance(a, dict):
            continue
        label = (a.get("label") or a.get("email") or "?").strip()
        email_ = (a.get("email") or a.get("sibleEmail") or a.get("identifier") or "").strip()
        sible_password = (a.get("siblePassword") or a.get("password") or "").strip()
        gmail_app = (a.get("gmailAppPassword") or a.get("gmailPass") or "").replace(" ", "").strip()

        missing = []
        if not email_: missing.append("email")
        if not sible_password: missing.append("siblePassword")
        if not gmail_app: missing.append("gmailAppPassword")
        if missing:
            raise ValueError(f'account "{label}" missing fields: {", ".join(missing)}')
        if len(gmail_app) != 16:
            raise ValueError(
                f'account "{label}": gmailAppPassword harus 16 karakter (got {len(gmail_app)}).\n'
                f'   Buat di: https://myaccount.google.com/apppasswords'
            )

        out.append({
            "label": label, "email": email_,
            "siblePassword": sible_password,
            "gmailAddress": email_,
            "gmailAppPassword": gmail_app,
        })
    return out


def append_csv(account, status, claimed):
    if not CFG.get("logCsv"):
        return
    f = CFG["csvFile"]
    if not os.path.exists(f):
        with open(f, "w", newline="", encoding="utf-8") as fp:
            fp.write("timestamp,label,username,balance,accumulated,rate,ads,boost,claimed,session,running\n")
    sess = status.get("session") or {}
    line = [
        datetime.now(timezone.utc).isoformat(),
        account.get("label", ""), account.get("username", ""),
        status.get("balance", ""), status.get("accumulatedAmount", ""),
        status.get("currentHourlyReward", ""),
        f"{sess.get('adsWatched', 0)}/{sess.get('adMaxPerSession', 0)}",
        sess.get("adBoostPct", 0), claimed or 0,
        sess.get("status", ""), 1 if sess.get("isRunning") else 0,
    ]
    with open(f, "a", newline="", encoding="utf-8") as fp:
        csv.writer(fp).writerow(line)


# ═══════════════════════════════════════════════════════════
#  RATE LIMIT
# ═══════════════════════════════════════════════════════════
_rate_limit_until = 0.0


async def rate_limit_wait():
    global _rate_limit_until
    now = time.time() * 1000
    if _rate_limit_until > now:
        wait = (_rate_limit_until - now) / 1000
        log(f"🛑 rate-limited, waiting {int(wait)}s")
        await sleep_sec(wait)


def trip_rate_limit():
    global _rate_limit_until
    _rate_limit_until = time.time() * 1000 + CFG["rateLimitBackoffSec"] * 1000


# ═══════════════════════════════════════════════════════════
#  HTTP
# ═══════════════════════════════════════════════════════════
_http_client: Optional[httpx.AsyncClient] = None


async def get_http():
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=30.0)
    return _http_client


async def raw(pathname, method="GET", body=None, token=None, headers_extra=None):
    await rate_limit_wait()
    ua = (headers_extra or {}).get("user-agent") or random_ua()
    ch = random_sec_ua(ua)
    headers = {
        "accept": "*/*", "accept-language": rnd(LANGS),
        "content-type": "application/json",
        "origin": ORIGIN, "referer": ORIGIN + "/",
        "sec-ch-ua": ch["sec-ch-ua"], "sec-ch-ua-mobile": ch["sec-ch-ua-mobile"],
        "sec-ch-ua-platform": ch["sec-ch-ua-platform"],
        "sec-fetch-dest": "empty", "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site", "user-agent": ua,
        "x-client-type": "web",
    }
    if headers_extra:
        headers.update(headers_extra)
    if token:
        headers["authorization"] = f"Bearer {token}"
    client = await get_http()
    try:
        r = await client.request(method, f"{BASE}{pathname}", headers=headers,
                                 json=body if body else None)
    except httpx.HTTPError as e:
        err = RuntimeError(f"network error on {pathname}: {e}")
        err.status = 0
        raise err
    if r.status_code == 429:
        trip_rate_limit()
        err = RuntimeError("HTTP 429 rate-limited")
        err.status = 429
        raise err
    text = r.text
    try:
        js = json.loads(text) if text else None
    except Exception:
        js = {"raw": text}
    if r.status_code >= 400:
        err = RuntimeError(f"HTTP {r.status_code} on {pathname}")
        err.status = r.status_code
        err.body = js
        raise err
    return js


# ═══════════════════════════════════════════════════════════
#  JWT
# ═══════════════════════════════════════════════════════════
def seconds_left(jwt):
    try:
        payload = jwt.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
        return int(data["exp"] - time.time())
    except Exception:
        return 0


# ═══════════════════════════════════════════════════════════
#  IMAP OTP FETCHER (EARLY RETURN)
# ═══════════════════════════════════════════════════════════
class ImapOtpFetcher:
    def __init__(self, cfg):
        self.host = cfg.get("imapHost", "imap.gmail.com")
        self.port = cfg.get("imapPort", 993)
        self.timeout = cfg.get("otpTimeoutSec", 120)
        self.poll = cfg.get("otpPollIntervalSec", 3)
        self.max_age = cfg.get("otpMaxAgeSec", 300)
        self.since_tolerance = cfg.get("otpSinceToleranceSec", 120)
        self.early_return_sec = cfg.get("earlyReturnSec", 60)

    def _decode_header(self, raw):
        if not raw:
            return ""
        try:
            parts = decode_header(raw)
            out = []
            for content, enc in parts:
                if isinstance(content, bytes):
                    try:
                        out.append(content.decode(enc or "utf-8", errors="ignore"))
                    except Exception:
                        out.append(content.decode("utf-8", errors="ignore"))
                else:
                    out.append(str(content))
            return "".join(out)
        except Exception:
            return str(raw)

    def _get_body(self, msg):
        body = ""
        try:
            if msg.is_multipart():
                for part in msg.walk():
                    ctype = part.get_content_type()
                    if ctype == "text/plain":
                        try:
                            payload = part.get_payload(decode=True)
                            if payload:
                                body += payload.decode("utf-8", errors="ignore")
                        except Exception:
                            pass
                    elif ctype == "text/html" and not body:
                        try:
                            payload = part.get_payload(decode=True)
                            if payload:
                                body += payload.decode("utf-8", errors="ignore")
                        except Exception:
                            pass
            else:
                payload = msg.get_payload(decode=True)
                if payload:
                    body = payload.decode("utf-8", errors="ignore")
        except Exception:
            pass
        return body

    def fetch_sync(self, gmail_address, gmail_app_password, since_ts):
        effective_since = since_ts - self.since_tolerance

        log(f"   📬 IMAP: connecting {self.host}:{self.port}...")
        log(f"   ⏱️ since_ts={int(since_ts)} effective_since={int(effective_since)} (tolerance {self.since_tolerance}s)")

        try:
            mail = imaplib.IMAP4_SSL(self.host, self.port)
            mail.login(gmail_address, gmail_app_password)
            mail.select("INBOX")
            log(f"   ✅ IMAP: logged in")
        except Exception as e:
            log(f"   ❌ IMAP login failed: {e}")
            return None

        try:
            deadline = time.time() + self.timeout
            attempt = 0

            while time.time() < deadline:
                attempt += 1

                since_date = (datetime.now() - timedelta(minutes=15)).strftime("%d-%b-%Y")
                try:
                    typ, data = mail.search(None, f'(SINCE "{since_date}")')
                except Exception:
                    typ, data = mail.search(None, "ALL")

                if typ != "OK":
                    log(f"   ⚠️ IMAP search failed: {typ}")
                    time.sleep(self.poll)
                    continue

                ids = data[0].split() if data and data[0] else []
                if not ids:
                    log(f"   attempt {attempt}: 0 email")
                    time.sleep(self.poll)
                    continue

                ids = ids[-30:][::-1]
                candidates = []

                # ═══════════════════════════════════════════════════
                #  SCAN EMAIL — dengan EARLY RETURN
                # ═══════════════════════════════════════════════════
                for eid in ids:
                    try:
                        typ, msg_data = mail.fetch(eid, "(RFC822)")
                        if typ != "OK" or not msg_data:
                            continue

                        for response_part in msg_data:
                            if not isinstance(response_part, tuple):
                                continue

                            msg = email.message_from_bytes(response_part[1])
                            from_ = self._decode_header(msg.get("From", ""))
                            subject = self._decode_header(msg.get("Subject", ""))
                            body = self._get_body(msg)

                            date_hdr = msg.get("Date", "")
                            email_ts = None
                            if date_hdr:
                                try:
                                    email_ts = parsedate_to_datetime(date_hdr).timestamp()
                                except Exception:
                                    pass

                            from_low = from_.lower()
                            subj_low = subject.lower()
                            body_low = body.lower()

                            log(f"      📧 from='{from_[:50]}'")
                            log(f"         subj='{subject[:60]}'")
                            if email_ts:
                                age = time.time() - email_ts
                                log(f"         ts_age={int(age)}s (email {int(age/60)}m lalu)")

                            # ─── FILTER ───
                            if "google.com" in from_low:
                                log(f"         ⏭️ skip: google.com")
                                continue
                            if "sible" not in from_low and "sible" not in subj_low:
                                log(f"         ⏭️ skip: bukan sible")
                                continue
                            if any(x in subj_low for x in ("reset", "password", "welcome")):
                                log(f"         ⏭️ skip: reset/password/welcome")
                                continue

                            looks_otp = (
                                "verification" in subj_low
                                or "code" in subj_low
                                or "otp" in subj_low
                                or "sign-in" in subj_low
                                or "verify" in subj_low
                                or "verification code" in body_low
                                or "your code" in body_low
                            )
                            if not looks_otp:
                                log(f"         ⏭️ skip: bukan OTP")
                                continue

                            if email_ts:
                                if email_ts < effective_since:
                                    delta = int(effective_since - email_ts)
                                    log(f"         ⏭️ skip: timestamp terlalu lama ({delta}s)")
                                    continue
                                if (time.time() - email_ts) > self.max_age:
                                    delta = int(time.time() - email_ts)
                                    log(f"         ⏭️ skip: expired ({delta}s > {self.max_age}s)")
                                    continue

                            log(f"         ✅ KANDIDAT!")

                            match = re.search(r"\b(\d{6})\b", body)
                            if not match:
                                match = re.search(r"\b(\d{6})\b", subject)
                            if match:
                                code = match.group(1)
                                age = (time.time() - email_ts) if email_ts else 9999
                                log(f"         🎯 code = {code} (age {int(age)}s)")

                                # simpan sebagai kandidat dulu
                                candidates.append({
                                    "code": code,
                                    "subject": subject,
                                    "date": email_ts or 0,
                                })

                                # ═══════════════════════════════════════
                                #  EARLY RETURN — STOP kalau sudah ada kandidat valid
                                #  (tidak perlu tunggu fresh, karena email
                                #   sudah lewat filter timestamp & max_age)
                                # ═══════════════════════════════════════
                                if EARLY_RETURN:
                                    if age <= self.early_return_sec:
                                        log(f"   ⚡ email fresh ({int(age)}s ≤ {self.early_return_sec}s) — STOP SCAN")
                                    else:
                                        log(f"   ⚡ kandidat valid ({int(age)}s) — STOP SCAN")
                                    log(f"   ✅ IMAP: OTP = {code} (\"{subject[:40]}\")")
                                    return code

                    except Exception as e:
                        log(f"      ⚠️ error parsing: {e}")
                        continue

                # ─── kalau tidak ada early return, sort & pilih ───
                if candidates:
                    candidates.sort(key=lambda x: x["date"], reverse=True)
                    pick = candidates[0]
                    log(f"   ✅ IMAP: OTP = {pick['code']} (\"{pick['subject'][:40]}\")")
                    return pick["code"]

                log(f"   attempt {attempt}: {len(ids)} email, 0 kandidat")
                time.sleep(self.poll)

            log(f"   ❌ IMAP: OTP timeout")
            return None
        finally:
            try:
                mail.logout()
            except Exception:
                pass

    async def fetch(self, gmail_address, gmail_app_password, since_ts):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self.fetch_sync, gmail_address, gmail_app_password, since_ts
        )


# ═══════════════════════════════════════════════════════════
#  LOGIN ONE (WITH RETRY)
# ═══════════════════════════════════════════════════════════
_imap_fetcher = None


def get_imap_fetcher():
    global _imap_fetcher
    if _imap_fetcher is None:
        _imap_fetcher = ImapOtpFetcher(CFG)
    return _imap_fetcher


async def login_one(cfg, view=None, max_retry=None):
    if max_retry is None:
        max_retry = CFG.get("loginMaxRetry", 2)
    retry_delay = CFG.get("loginRetryDelaySec", 10)

    label = cfg["label"]
    email_ = cfg["email"]
    password = cfg["siblePassword"]
    gmail_address = cfg.get("gmailAddress") or email_
    gmail_app = cfg["gmailAppPassword"]

    for attempt in range(1, max_retry + 1):
        log(f"🔐 {label} ({email_}) — attempt {attempt}/{max_retry}")
        if view:
            set_status(view, "🔐", "blue", "login", f"{attempt}/{max_retry}")

        ua = random_ua()

        set_status(view, "🔐", "blue", "login Sible")
        log(f"🔐 POST /auth/login...")
        login_started = time.time()
        try:
            login_resp = await raw("/auth/login", method="POST",
                                   body={"identifier": email_, "password": password},
                                   headers_extra={"user-agent": ua})
        except RuntimeError as e:
            set_status(view, "❌", "red", "login failed", str(e)[:40])
            log(f"❌ login: {e}")
            if view:
                view.error = str(e)[:50]
            if attempt < max_retry:
                log(f"🔄 retry dalam {retry_delay}s...")
                await sleep_sec(retry_delay)
                continue
            return None

        if not (login_resp.get("data") or {}).get("needsOtp"):
            set_status(view, "⚠️", "yellow", "unexpected response")
            log(f"⚠️ needsOtp false")
            if attempt < max_retry:
                log(f"🔄 retry dalam {retry_delay}s...")
                await sleep_sec(retry_delay)
                continue
            return None

        otp_email = login_resp["data"].get("email") or email_
        log(f"📧 OTP → {otp_email}")

        set_status(view, "📬", "yellow", "reading OTP", "(IMAP)")
        log(f"📬 IMAP scan OTP...")
        try:
            fetcher = get_imap_fetcher()
            code = await fetcher.fetch(gmail_address, gmail_app, login_started)
        except Exception as e:
            set_status(view, "❌", "red", "OTP failed", str(e)[:40])
            log(f"❌ IMAP failed: {e}")
            if attempt < max_retry:
                log(f"🔄 retry dalam {retry_delay}s...")
                await sleep_sec(retry_delay)
                continue
            return None

        if not code:
            set_status(view, "❌", "red", "OTP not found")
            log(f"❌ OTP tidak ketemu")
            if attempt < max_retry:
                log(f"🔄 retry dalam {retry_delay}s...")
                await sleep_sec(retry_delay)
                continue
            return None

        log(f"✅ OTP: {code}")

        set_status(view, "🔐", "blue", "verifying OTP")
        try:
            verify_resp = await raw("/auth/verify-otp", method="POST",
                                    body={"email": otp_email, "code": code, "purpose": "login"},
                                    headers_extra={"user-agent": ua})
        except RuntimeError as e:
            set_status(view, "❌", "red", "verify failed", str(e)[:40])
            log(f"❌ verify: {e}")
            if attempt < max_retry:
                log(f"🔄 retry dalam {retry_delay}s...")
                await sleep_sec(retry_delay)
                continue
            return None

        d = verify_resp.get("data") or {}
        if not d.get("accessToken"):
            set_status(view, "❌", "red", "no token")
            if attempt < max_retry:
                await sleep_sec(retry_delay)
                continue
            return None

        username = d["user"]["username"]
        balance = d["user"].get("balance", 0)
        log(f"✅ {username}  bal={balance}")
        if view:
            view.username = username
            view.balance = balance
            set_status(view, "✅", "green", "logged in", username)

        return {
            "label": label, "identifier": email_,
            "email": d["user"]["email"], "username": username,
            "userId": d["user"]["id"],
            "accessToken": d["accessToken"],
            "refreshToken": d.get("refreshToken", ""),
            "savedAt": datetime.now(timezone.utc).isoformat(),
            "refreshedAt": datetime.now(timezone.utc).isoformat(),
            "user": d["user"],
        }

    log(f"❌ {label}: login failed after {max_retry} attempts")
    return None


# ═══════════════════════════════════════════════════════════
#  REFRESH / RELOGIN / CALL WITH AUTH
# ═══════════════════════════════════════════════════════════
_refresh_locks: dict = {}


async def refresh_account(account, store):
    key = account.get("label") or account.get("username")
    while _refresh_locks.get(key):
        await _refresh_locks[key]
    future = asyncio.get_event_loop().create_future()
    _refresh_locks[key] = future
    try:
        left = seconds_left(account.get("accessToken", ""))
        if left > 60:
            return account
        endpoint = CFG.get("refreshEndpoint") or "/auth/refresh"
        r = await raw(endpoint, method="POST",
                      body={"refreshToken": account.get("refreshToken", "")})
        d = r.get("data") or {}
        if not d.get("accessToken"):
            raise RuntimeError("refresh: no accessToken")
        account["accessToken"] = d["accessToken"]
        if d.get("refreshToken"):
            account["refreshToken"] = d["refreshToken"]
        account["refreshedAt"] = datetime.now(timezone.utc).isoformat()
        save_store(store)
        return account
    finally:
        _refresh_locks.pop(key, None)
        if not future.done():
            future.set_result(True)


async def ensure_fresh(account, store, view=None):
    left = seconds_left(account.get("accessToken", ""))
    if left > 300:
        return
    set_status(view, "🔄", "cyan", "refresh token", f"exp {left}s")
    try:
        await refresh_account(account, store)
    except Exception as e:
        if getattr(e, "status", 0) == 401 and CFG.get("reloginOn401") and CFG.get("autoRelogin"):
            set_status(view, "🔁", "cyan", "relogin")
            await relogin_account(account, store, view)
        else:
            raise


async def relogin_account(account, store, view=None):
    accounts = load_accounts(ACCOUNTS_FILE)
    cfg = None
    for a in accounts:
        if (a["email"] == account.get("email")
            or a["email"] == account.get("identifier")
            or a["label"] == account.get("label")):
            cfg = a
            break
    if not cfg:
        raise RuntimeError(f"no matching entry")
    fresh = await login_one(cfg, view)
    if not fresh:
        raise RuntimeError("relogin failed")
    account.update(fresh)
    save_store(store)
    return account


async def silent_referral(account):
    if not CFG.get("referralCode"):
        return False
    try:
        me = await raw("/users/me", token=account.get("accessToken"))
        if (me.get("data") or {}).get("referredBy"):
            return False
        await raw("/referral/apply", method="POST",
                  body={"code": CFG["referralCode"]},
                  token=account.get("accessToken"))
        return True
    except Exception:
        return False


async def call_with_auth(pathname, account, store, opts=None, view=None):
    opts = opts or {}
    try:
        return await raw(pathname, token=account.get("accessToken"),
                         method=opts.get("method", "GET"), body=opts.get("body"))
    except RuntimeError as e:
        if getattr(e, "status", 0) != 401:
            raise
        try:
            await refresh_account(account, store)
            return await raw(pathname, token=account.get("accessToken"),
                             method=opts.get("method", "GET"), body=opts.get("body"))
        except Exception as e2:
            if not (CFG.get("reloginOn401") and CFG.get("autoRelogin")):
                raise e2
            await relogin_account(account, store, view)
            return await raw(pathname, token=account.get("accessToken"),
                             method=opts.get("method", "GET"), body=opts.get("body"))


def extract_next_ad_at(err_body):
    if not err_body:
        return None
    paths = []
    def get(d, *keys):
        for k in keys:
            if not isinstance(d, dict):
                return None
            d = d.get(k)
        return d
    try:
        details = get(err_body, "error", "details")
        if isinstance(details, list) and details:
            paths.append(get(details[0], "nextAdAt"))
            paths.append(get(details[0], "data", "nextAdAt"))
    except Exception:
        pass
    paths.append(get(err_body, "error", "nextAdAt"))
    paths.append(get(err_body, "error", "data", "nextAdAt"))
    paths.append(get(err_body, "details", "nextAdAt"))
    paths.append(get(err_body, "nextAdAt"))
    paths.append(get(err_body, "data", "nextAdAt"))
    paths.append(get(err_body, "data", "session", "nextAdAt"))
    for p in paths:
        if not p:
            continue
        try:
            return datetime.fromisoformat(p.replace("Z", "+00:00")).timestamp() * 1000
        except Exception:
            continue
    return None


# ═══════════════════════════════════════════════════════════
#  CYCLE
# ═══════════════════════════════════════════════════════════
async def cycle(account, store, view=None):
    tag = account.get("label") or account.get("username")
    await ensure_fresh(account, store, view)
    await silent_referral(account)

    set_status(view, "🚀", "cyan", "checking status")
    d0 = (await call_with_auth("/mining/status", account, store, view=view))["data"]
    s0 = d0.get("session") or {}

    if d0.get("canActivate") and not s0.get("isRunning"):
        try:
            set_status(view, "🚀", "cyan", "starting session")
            await call_with_auth("/mining/start", account, store, {"method": "POST"}, view)
            log(f"[{tag}] 🚀 session started")
        except RuntimeError as e:
            log(f"[{tag}] ⚠️ start: {e}")

    cap = s0.get("adMaxPerSession") or d0.get("adMaxPerSession") or 3
    watched = s0.get("adsWatched") or 0
    attempts_409 = 0
    MAX_409 = 6
    if view:
        view.ads_max = cap
        view.ads_watched = watched

    while watched < cap:
        try:
            set_status(view, "📺", "magenta", "watching ads", f"{watched}/{cap}")
            r = await call_with_auth("/mining/ad", account, store, {"method": "POST"}, view)
            watched = (r.get("data", {}).get("session") or {}).get("adsWatched", watched + 1)
            boost = (r.get("data", {}).get("session") or {}).get("adBoostPct", 0)
            log(f"[{tag}] 📺 ad {watched}/{cap} +{boost}%")
            if view:
                view.ads_watched = watched
                view.boost_pct = boost
            set_status(view, "📺", "magenta", "watching ads", f"{watched}/{cap} +{boost}%")
            attempts_409 = 0
        except RuntimeError as e:
            status = getattr(e, "status", 0)
            if status == 429:
                set_status(view, "🛑", "red", "rate limited", "30s")
                await sleep_sec(30)
                continue
            if status == 409:
                code = ((getattr(e, "body", None) or {}).get("error") or {}).get("code", "")
                if code == "AD_CLAIM_REQUIRED":
                    break
                attempts_409 += 1
                if attempts_409 > MAX_409:
                    break
                next_at = extract_next_ad_at(getattr(e, "body", None))
                if not next_at:
                    try:
                        st = (await call_with_auth("/mining/status", account, store, view=view))["data"]
                        if (st.get("session") or {}).get("nextAdAt"):
                            next_at = datetime.fromisoformat(
                                st["session"]["nextAdAt"].replace("Z", "+00:00")
                            ).timestamp() * 1000
                    except Exception:
                        pass
                if next_at and next_at > time.time() * 1000:
                    wait_ms = min(max(3000, next_at - time.time() * 1000 + rand_int(1000, 3000)),
                                  5 * 60 * 1000)
                    set_status(view, "⏳", "yellow", "next ad", f"{int(wait_ms/1000)}s")
                    await sleep_sec(wait_ms / 1000)
                    continue
                set_status(view, "⏳", "yellow", "409 wait", "60s")
                await sleep_sec(60)
                continue
            set_status(view, "⚠️", "yellow", "ad error", str(e)[:30])
            break
        if watched < cap:
            await sleep_sec(10)

    set_status(view, "💰", "yellow", "checking claim")
    fresh = (await call_with_auth("/mining/status", account, store, view=view))["data"]
    claimed = 0

    if fresh.get("canClaim") and (fresh.get("claimableAmount") or 0) > 0:
        try:
            set_status(view, "💰", "yellow", "claiming")
            start = await call_with_auth("/mining/claim", account, store, {"method": "POST"}, view)
            claim_id = (start.get("data") or {}).get("claimId")
            final = None
            for i in range(10):
                await sleep_sec(3)
                set_status(view, "💰", "yellow", "claiming", f"poll {i+1}/10")
                r = await call_with_auth(f"/mining/claim/{claim_id}", account, store, view=view)
                final = r.get("data")
                if final and final.get("status") in ("completed", "failed"):
                    break
            if final and final.get("status") == "completed":
                account["user"]["balance"] = final["balanceAfter"]
                claimed = final["amount"]
                log(f"[{tag}] 💰 claimed {fmt(final['amount'])} → {fmt(final['balanceAfter'])}")
                await notify_webhook(f"💰 **{tag}** claimed {fmt(final['amount'])} → {fmt(final['balanceAfter'])}")
                if view:
                    view.balance = final["balanceAfter"]
        except RuntimeError as e:
            log(f"[{tag}] ⚠️ claim: {e}")

    after = (await call_with_auth("/mining/status", account, store, view=view))["data"]
    s = after.get("session") or {}
    if view:
        view.balance = after.get("balance", view.balance)
        view.rate = after.get("currentHourlyReward", 0)
        view.ads_watched = s.get("adsWatched", 0)
        view.ads_max = s.get("adMaxPerSession", 3)
        view.boost_pct = s.get("adBoostPct", 0)
        view.running = bool(s.get("isRunning"))

    log(f"[{tag}] bal={fmt(after.get('balance'))}  "
        f"{'✓' if s.get('isRunning') else '✗'}  "
        f"ads={s.get('adsWatched', 0)}/{s.get('adMaxPerSession', 3)}  "
        f"+{s.get('adBoostPct', 0)}%  {fmt(after.get('currentHourlyReward'))}/hr")

    append_csv(account, after, claimed)
    save_store(store)

    ads_done = (s.get("adsWatched") or 0) >= (s.get("adMaxPerSession") or 3)
    if not ads_done and s.get("isRunning"):
        return time.time() * 1000 + rand_int(40000, 90000)

    events = []
    if s.get("nextAdAt"):
        try:
            events.append(datetime.fromisoformat(s["nextAdAt"].replace("Z", "+00:00")).timestamp() * 1000)
        except Exception:
            pass
    if s.get("endsAt"):
        try:
            events.append(datetime.fromisoformat(s["endsAt"].replace("Z", "+00:00")).timestamp() * 1000)
        except Exception:
            pass
    now_ms = time.time() * 1000
    future = [e for e in events if e > now_ms]
    if future:
        return min(future)
    return None


async def notify_webhook(msg):
    if not CFG.get("discordWebhook"):
        return
    try:
        client = await get_http()
        await client.post(CFG["discordWebhook"], json={"content": msg})
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════
#  ACCOUNT WORKER
# ═══════════════════════════════════════════════════════════
async def account_worker(account, store, view):
    if not account.get("accessToken"):
        cfg = None
        for a in load_accounts(ACCOUNTS_FILE):
            if a["label"] == account.get("label"):
                cfg = a
                break
        if cfg:
            fresh = await login_one(cfg, view)
            if fresh:
                account.update(fresh)
                save_store(store)
            else:
                set_status(view, "❌", "red", "login failed")
                return

    while True:
        try:
            if view:
                view.cycles += 1
            soonest = await cycle(account, store, view)
            if soonest:
                wait_ms = max(10000, soonest - time.time() * 1000 + rand_int(2000, 8000))
            else:
                wait_ms = INTERVAL
            wait_ms = min(wait_ms, INTERVAL)
            jitter = rand_int(-CFG["jitterSec"] * 1000, CFG["jitterSec"] * 1000)
            wait_ms = max(10000, wait_ms + jitter)
            wait_s = int(wait_ms / 1000)
            if view:
                view.next_wake = time.time() + wait_s
                set_status(view, "💤", "grey50", "sleeping", f"{wait_s}s")
            log(f"[{account.get('label')}] 💤 sleeping {wait_s}s...")
            await sleep_sec(wait_ms / 1000)
            if not LOOP:
                break
        except Exception as e:
            set_status(view, "❌", "red", "error", str(e)[:40])
            log(f"[{account.get('label')}] ❌ {e}")
            await notify_webhook(f"❌ **{account.get('label')}** {e}")
            await sleep_sec(60)


# ═══════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════
async def amain():
    init_log()
    console = Console()

    try:
        account_cfg = load_accounts(ACCOUNTS_FILE)
    except Exception as e:
        console.print(f"[red]❌ {e}[/red]")
        sys.exit(1)
    if not account_cfg:
        console.print("[red]❌ no accounts[/red]")
        sys.exit(1)
    if ONLY:
        account_cfg = [c for c in account_cfg if c["label"] == ONLY or c["email"] == ONLY]
    if EXCLUDE:
        account_cfg = [c for c in account_cfg if c["label"] != EXCLUDE and c["email"] != EXCLUDE]
    if not account_cfg:
        console.print("[red]❌ no accounts after filter[/red]")
        sys.exit(1)

    store = load_store()
    accounts = store.get("accounts", [])
    views = [AccountView(c["label"], c["email"]) for c in account_cfg]

    for i, c in enumerate(account_cfg):
        for a in accounts:
            if (a.get("label") == c["label"]
                or a.get("email") == c["email"]
                or a.get("identifier") == c["email"]):
                views[i].username = a.get("username", "")
                views[i].balance = (a.get("user") or {}).get("balance", 0)
                set_status(views[i], "⏳", "grey50", "starting")
                break

    dashboard = Dashboard(console, views)
    dashboard_task = asyncio.create_task(dashboard.run())

    for i, c in enumerate(account_cfg):
        found = False
        for a in accounts:
            if (a.get("label") == c["label"]
                or a.get("email") == c["email"]
                or a.get("identifier") == c["email"]):
                found = True
                break
        if not found:
            fresh = await login_one(c, views[i])
            if fresh:
                accounts.append(fresh)
                store["accounts"] = accounts
                save_store(store)

    workers = []
    for i, c in enumerate(account_cfg):
        acc = None
        for a in accounts:
            if (a.get("label") == c["label"]
                or a.get("email") == c["email"]
                or a.get("identifier") == c["email"]):
                acc = a
                break
        if acc:
            workers.append(asyncio.create_task(account_worker(acc, store, views[i])))

    if not workers:
        console.print("[red]❌ no workers[/red]")
        dashboard.stop = True
        try:
            await asyncio.wait_for(dashboard_task, timeout=3)
        except Exception:
            pass
        sys.exit(1)

    try:
        await asyncio.gather(*workers)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        dashboard.stop = True
        try:
            await asyncio.wait_for(dashboard_task, timeout=3)
        except Exception:
            pass
        for w in workers:
            w.cancel()
        await asyncio.gather(*workers, return_exceptions=True)
        save_store(store)
        global _http_client
        if _http_client:
            try:
                await _http_client.aclose()
            except Exception:
                pass


def main():
    try:
        asyncio.run(amain())
    except KeyboardInterrupt:
        pass
    finally:
        close_log()


if __name__ == "__main__":
    main()
