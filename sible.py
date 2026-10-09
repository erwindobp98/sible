import asyncio
import base64
import csv
import json
import os
import random
import re
import sys
import time
from datetime import datetime, timezone
from typing import Optional

import httpx
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.console import Console, Group
from rich.text import Text

# ═══════════════════════════════════════════════════════════
#  CONSTANTS
# ═══════════════════════════════════════════════════════════
BASE = "https://prod.sible.network/api/v1"
ORIGIN = "https://mine.sible.network"
SESSIONS_DIR = "sessions"

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
        "add": flag("add"),
        "reset_session": has("reset-session"),
        "once": has("once"), "loop": has("loop"),
        "quiet": has("quiet"), "debug_refresh": has("debug-refresh"),
    }


ARGV = parse_argv()
AUTH_FILE = ARGV["file"]
CONFIG_FILE = ARGV["config"]
ACCOUNTS_FILE = ARGV["accounts"]
ONLY = ARGV["only"]
EXCLUDE = ARGV["exclude"]
ADD_LABEL = ARGV["add"]
RESET_SESSION = ARGV["reset_session"]


# ═══════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════
DEFAULTS = {
    "referralCode": "", "interval": 3600, "jitterSec": 3,
    "minDelayBetweenAccountsSec": 2, "maxDelayBetweenAccountsSec": 6,
    "rateLimitBackoffSec": 30, "refreshEndpoint": "/auth/refresh",
    "autoRelogin": True, "reloginOn401": True, "logCsv": True,
    "csvFile": "mining-log.csv", "discordWebhook": "", "quiet": False,
    "debugRefresh": True,

    "setupMode": "normal",
    "purgeMode": "headless",
    "otpMode": "headless",

    "setupTimeoutSec": 1800,
    "otpTimeoutSec": 180,
    "otpPollIntervalSec": 5,
    "sessionsDir": "sessions",
    "deleteOldSibleEmails": True,
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
    try:
        print(line, flush=True)
    except Exception:
        pass
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
        from rich.columns import Columns
        from rich.console import Group

        now = time.time()

        # ═══ BIKIN PANEL PER AKUN ═══
        panels = []
        for v in self.views:
            # ─── isi panel ───
            lines = []

            # Status (icon + text + detail)
            status_str = self._build_status_cell(v)
            lines.append(f"[grey50]Status [/grey50]  : {status_str}")

            # Balance
            bal = fmt(v.balance) if v.balance else "-"
            lines.append(f"[grey50]Balance[/grey50]  : [green]{bal}[/green]")

            # Rate
            rate = fmt(v.rate) if v.rate else "-"
            lines.append(f"[grey50]Rate/hr[/grey50]  : [green]{rate}[/green]")

            # Ads + Boost + Run (1 baris)
            ads = f"{v.ads_watched}/{v.ads_max}"
            boost = f"+{v.boost_pct}%"
            run = "[green]✓[/green]" if v.running else "[red]✗[/red]"
            lines.append(
                f"[grey50]Ads[/grey50]      : [magenta]{ads}[/magenta]"
                f"   [grey50]Boost[/grey50] : [green]{boost}[/green]"
                f"   [grey50]Run[/grey50] : {run}"
            )

            # Cycle + Next
            next_in = ""
            if v.next_wake > now:
                next_in = f"{int(v.next_wake - now)}s"
            elif v.next_wake > 0:
                next_in = "now"
            lines.append(
                f"[grey50]Cycle[/grey50]    : {v.cycles}"
                f"   [grey50]Next[/grey50] : {next_in or '-'}"
            )

            # Error / last msg
            err = v.error or v.last_msg or ""
            if err:
                lines.append(f"[red]{err[:60]}[/red]")

            content = "\n".join(lines)

            # ─── title panel = username ───
            title = f"[bold cyan]{v.username or v.label}[/bold cyan]"

            # ─── subtitle = status login ───
            if v.username and v.balance > 0:
                subtitle = "[green]logged in[/green]"
            elif v.status_text in ("login failed", "error"):
                subtitle = "[red]failed[/red]"
            else:
                subtitle = "[yellow]starting[/yellow]"

            panel = Panel(
                content,
                title=title,
                subtitle=subtitle,
                title_align="left",
                subtitle_align="right",
                border_style="grey50",
                padding=(0, 1),
            )
            panels.append(panel)

        # ═══ GABUNG VERTIKAL ═══
        if panels:
            body = Group(*panels)
        else:
            body = Text("(no accounts)", style="grey50")

        # ═══ PANEL BESAR ═══
        return Panel(
            body,
            title="[bold cyan]⛏️  SIBLE MINING[/bold cyan]",
            title_align="left",
            border_style="cyan",
            padding=(1, 1),
        )

    async def run(self):
        """Jalankan dashboard dengan Rich Live."""
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
            "email": "user1@gmail.com",
            "siblePassword": "passwordSible1",
            "gmailPassword": "passwordGmail1"
        }
    ]
}


def load_accounts(file):
    if not os.path.exists(file):
        with open(file, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_ACCOUNTS, f, indent=4)
        print(f"📝 Generated {file} — isi akun, lalu jalankan ulang.")
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
        email = (a.get("email") or a.get("sibleEmail") or a.get("identifier") or "").strip()
        sible_password = (a.get("siblePassword") or a.get("password") or "").strip()
        gmail_address = (a.get("gmailAddress") or a.get("gmailUser") or email).strip()
        gmail_password = (a.get("gmailPassword") or a.get("gmailPass") or "").strip()
        missing = []
        if not email: missing.append("email")
        if not sible_password: missing.append("siblePassword")
        if not gmail_address: missing.append("gmailAddress")
        if not gmail_password: missing.append("gmailPassword")
        if missing:
            raise ValueError(f'account "{label}" missing fields: {", ".join(missing)}')
        out.append({
            "label": label, "email": email,
            "siblePassword": sible_password,
            "gmailAddress": gmail_address,
            "gmailPassword": gmail_password,
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
#  SESSION DIR
# ═══════════════════════════════════════════════════════════
def get_session_dir(label):
    safe = re.sub(r'[^a-zA-Z0-9_.-]', '_', label)
    return os.path.join(CFG.get("sessionsDir", SESSIONS_DIR), safe)


def has_session(label):
    d = get_session_dir(label)
    if not os.path.isdir(d):
        return False
    try:
        return len(os.listdir(d)) > 0
    except Exception:
        return False


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
#  SETUP GOOGLE SESSION (manual + close manual)
# ═══════════════════════════════════════════════════════════
async def setup_google_session(cfg, view=None):
    """
    Alur:
    1. Buka Chromium (mode setupMode)
    2. Auto-isi email + password (kalau form ketemu)
    3. TUNGGU user selesaikan manual (consent, 2FA, dll)
    4. TUNGGU user CLOSE Chromium manual
    5. Setelah close → simpan session + verifikasi login
    """
    from playwright.async_api import async_playwright

    label = cfg["label"]
    gmail_address = cfg.get("gmailAddress") or cfg["email"]
    gmail_password = cfg["gmailPassword"]
    profile = get_session_dir(label)

    # ─── backup folder lama (kalau ada) ───
    if os.path.exists(profile):
        backup = f"{profile}_backup_{int(time.time())}"
        try:
            import shutil
            shutil.move(profile, backup)
            log(f"📦 backup session lama → {backup}")
        except Exception as e:
            log(f"⚠️ backup gagal: {e}")
            import shutil
            shutil.rmtree(profile, ignore_errors=True)

    os.makedirs(profile, exist_ok=True)

    mode = CFG.get("setupMode", "normal").lower()
    log(f"")
    log(f"╔════════════════════════════════════════════════════╗")
    log(f"║   🔐 SETUP GOOGLE SESSION — {label:<20}       ║")
    log(f"╚════════════════════════════════════════════════════╝")
    log(f"   mode      : {mode}")
    log(f"   email     : {gmail_address}")
    log(f"   profile   : {profile}")
    log(f"")
    log(f"   ⚠️  PENTING:")
    log(f"   1. Script akan auto-isi email + password")
    log(f"   2. SELESAIKAN consent screen manual di browser")
    log(f"   3. TUTUP BROWSER manual kalau sudah di inbox")
    log(f"   4. Session disimpan SETELAH browser ditutup")
    log(f"")

    if view:
        set_status(view, "🔐", "blue", "setup manual", "popup")

    async with async_playwright() as p:
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-default-browser-check",
        ]
        if mode == "offscreen":
            launch_args.extend(["--window-position=-2400,-2400", "--window-size=1280,800"])
        elif mode == "minimized":
            launch_args.extend(["--start-minimized", "--window-size=1280,800"])
        else:
            launch_args.extend(["--window-size=1280,800"])

        context = await p.chromium.launch_persistent_context(
            user_data_dir=profile,
            headless=(mode == "headless"),
            args=launch_args,
            viewport={"width": 1280, "height": 800},
            locale="en-US",
            timezone_id="Asia/Jakarta",
        )

        try:
            page = context.pages[0] if context.pages else await context.new_page()
            for pg in context.pages[1:]:
                try:
                    await pg.close()
                except Exception:
                    pass

            # ─── goto Gmail ───
            log(f"   🌐 goto Gmail...")
            try:
                await page.goto("https://mail.google.com/mail/u/0/#inbox",
                                wait_until="domcontentloaded", timeout=60000)
            except Exception as e:
                log(f"   ⚠️ goto error: {e}")
            await page.wait_for_timeout(3000)

            # ─── deteksi halaman & auto-isi ───
            await _handle_login_page(page, gmail_address, gmail_password, view)

            # ─── TUNGGU USER CLOSE BROWSER MANUAL ───
            log(f"")
            log(f"   ⏳ TUNGGU USER:")
            log(f"      - Selesaikan login/consent di browser")
            log(f"      - CLOSE BROWSER manual kalau sudah di inbox")
            log(f"")

            if view:
                set_status(view, "⏳", "yellow", "waiting manual", "close browser")

            # monitor: tunggu sampai browser close
            # context.on("close") di Playwright async tidak reliable
            # → polling page.closed / context pages
            browser_closed = False
            consent_done = False
            start_wait = time.time()
            setup_timeout = CFG.get("setupTimeoutSec", 1800)

            while time.time() - start_wait < setup_timeout:
                try:
                    # cek: apakah browser sudah closed?
                    if context.pages:
                        # masih ada page, cek apakah sudah di inbox
                        all_pages = context.pages
                        if not all_pages:
                            browser_closed = True
                            break

                        # cek page utama
                        main_page = all_pages[0]
                        try:
                            url = main_page.url
                        except Exception:
                            url = ""

                        # cek apakah sudah di inbox (untuk log saja)
                        if "mail.google.com/mail/u/" in url and not consent_done:
                            # cek elemen inbox
                            try:
                                compose = await main_page.query_selector('div[gh="cm"]')
                                if compose:
                                    consent_done = True
                                    log(f"   ✅ inbox terdeteksi — silakan CLOSE browser")
                                    if view:
                                        set_status(view, "✅", "green", "inbox OK", "close browser")
                            except Exception:
                                pass
                    else:
                        browser_closed = True
                        break
                except Exception:
                    # kalau ada exception → mungkin browser closed
                    browser_closed = True
                    break

                await asyncio.sleep(2)

            # ─── tutup context (kalau belum) ───
            try:
                await context.close()
            except Exception:
                pass

            log(f"")
            log(f"   🍪 Chromium closed")

            # ─── verifikasi session ───
            if not consent_done:
                log(f"   ⚠️ inbox tidak terdeteksi — verifikasi manual...")
                # tetap cek folder
                if not has_session(label):
                    log(f"   ❌ session folder kosong")
                    if view:
                        set_status(view, "❌", "red", "setup failed")
                    return False

            log(f"   ✅ Session tersimpan di: {profile}")
            log(f"   ✅ Sekarang jalankan: python sible.py --only={label}")

            if view:
                set_status(view, "✅", "green", "session saved")

            return True

        except Exception as e:
            log(f"   ❌ setup error: {e}")
            try:
                await context.close()
            except Exception:
                pass
            if view:
                set_status(view, "❌", "red", "setup error", str(e)[:30])
            return False


async def _handle_login_page(page, email, password, view=None):
    """
    Auto-isi form login kalau ketemu.
    Loop sampai email+password terisi ATAU sudah di inbox.
    """
    log(f"   🔍 handle login page...")
    deadline = time.time() + 60
    email_filled = False
    password_filled = False

    while time.time() < deadline:
        try:
            url = page.url
            log(f"   🌐 url: {url}")

            # ─── sudah di inbox? berhenti ───
            if "mail.google.com/mail/u/" in url:
                try:
                    compose = await page.query_selector('div[gh="cm"]')
                    if compose:
                        log(f"   ✅ sudah di inbox")
                        return True
                except Exception:
                    pass

            # ─── workspace.google.com → cari tombol Sign in ───
            if "workspace.google.com" in url:
                log(f"   ⚠️ workspace page")
                clicked = False
                for sel in ['a:has-text("Sign in")', 'a:has-text("Masuk")',
                            'a[href*="accounts.google.com"]']:
                    try:
                        btn = await page.query_selector(sel)
                        if btn and await btn.is_visible():
                            await btn.click()
                            clicked = True
                            log(f"   ✅ clicked: {sel}")
                            await page.wait_for_timeout(3000)
                            break
                    except Exception:
                        continue
                if not clicked:
                    try:
                        await page.goto("https://accounts.google.com/signin",
                                        wait_until="domcontentloaded", timeout=30000)
                        await page.wait_for_timeout(2000)
                    except Exception:
                        pass
                continue

            # ─── isi email ───
            if not email_filled:
                email_input = None
                for sel in ['input[type="email"]', 'input[name="identifier"]',
                            'input[autocomplete="username"]', 'input#identifierId']:
                    try:
                        email_input = await page.wait_for_selector(sel, timeout=2000, state="visible")
                        if email_input:
                            break
                    except Exception:
                        continue

                if email_input:
                    log(f"   📧 auto-isi email: {email}")
                    if view:
                        set_status(view, "📧", "blue", "auto-isi email")
                    await email_input.click()
                    await email_input.fill(email)
                    await page.wait_for_timeout(500)

                    for sel in ['#identifierNext', 'button:has-text("Next")',
                                'button:has-text("Berikutnya")']:
                        try:
                            btn = await page.query_selector(sel)
                            if btn and await btn.is_visible():
                                await btn.click()
                                break
                        except Exception:
                            continue
                    else:
                        await email_input.press("Enter")

                    email_filled = True
                    log(f"   ✅ email diisi")
                    await page.wait_for_timeout(4000)
                    continue

            # ─── isi password ───
            if email_filled and not password_filled:
                pwd_input = None
                for sel in ['input[type="password"]', 'input[name="Passwd"]',
                            'input[name="password"]']:
                    try:
                        pwd_input = await page.wait_for_selector(sel, timeout=3000, state="visible")
                        if pwd_input:
                            break
                    except Exception:
                        continue

                if pwd_input:
                    log(f"   🔑 auto-isi password")
                    if view:
                        set_status(view, "🔑", "blue", "auto-isi password")
                    await pwd_input.click()
                    await pwd_input.fill(password)
                    await page.wait_for_timeout(500)

                    for sel in ['#passwordNext', 'button:has-text("Next")',
                                'button:has-text("Berikutnya")']:
                        try:
                            btn = await page.query_selector(sel)
                            if btn and await btn.is_visible():
                                await btn.click()
                                break
                        except Exception:
                            continue
                    else:
                        await pwd_input.press("Enter")

                    password_filled = True
                    log(f"   ✅ password diisi — silakan lanjutkan manual")
                    if view:
                        set_status(view, "⏳", "yellow", "lanjutkan manual")
                    await page.wait_for_timeout(3000)
                    return True  # ← stop auto-isi, tunggu user manual

        except Exception as e:
            log(f"   ⚠️ handle error: {e}")

        await asyncio.sleep(2)

    return False


# ═══════════════════════════════════════════════════════════
#  PURGE OLD SIBLE EMAILS (headless)
# ═══════════════════════════════════════════════════════════
async def purge_old_sible_emails(cfg, view=None):
    from playwright.async_api import async_playwright

    label = cfg["label"]
    profile = get_session_dir(label)
    if not has_session(label):
        return False

    mode = CFG.get("purgeMode", "headless").lower()
    log(f"🗑️ purge email lama (mode={mode})...")

    async with async_playwright() as p:
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-first-run", "--no-default-browser-check",
        ]
        if mode == "offscreen":
            launch_args.extend(["--window-position=-2400,-2400", "--window-size=1280,800"])
        elif mode == "minimized":
            launch_args.extend(["--start-minimized", "--window-size=1280,800"])
        else:
            launch_args.append("--window-size=1280,800")

        context = await p.chromium.launch_persistent_context(
            user_data_dir=profile,
            headless=(mode == "headless"),
            args=launch_args,
            viewport={"width": 1280, "height": 800},
            locale="en-US", timezone_id="Asia/Jakarta",
        )
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto("https://mail.google.com/mail/u/0/#inbox",
                            wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(5000)

            if "mail.google.com/mail" not in page.url:
                return False

            deleted = 0
            for _ in range(10):
                rows = []
                try:
                    rows = await page.query_selector_all("tr.zA")
                except Exception:
                    break
                if not rows:
                    break

                target_row = None
                for row in rows[:20]:
                    try:
                        s_el = await row.query_selector(".yX.xY .yP, .zF")
                        j_el = await row.query_selector(".y6 span")
                        s = (await s_el.inner_text()).strip().lower() if s_el else ""
                        j = (await j_el.inner_text()).strip().lower() if j_el else ""
                        if "sible" in s or "sible" in j:
                            target_row = row
                            break
                    except Exception:
                        continue

                if not target_row:
                    break

                try:
                    cb = await target_row.query_selector('div[role="checkbox"]')
                    if not cb:
                        cb = await target_row.query_selector('input[type="checkbox"]')
                    if cb:
                        await cb.click()
                        await page.wait_for_timeout(600)
                        delete_btn = await page.query_selector('div[aria-label*="Hapus"]')
                        if not delete_btn:
                            delete_btn = await page.query_selector('div[aria-label*="Delete"]')
                        if delete_btn:
                            await delete_btn.click()
                        else:
                            await page.keyboard.press("Delete")
                        await page.wait_for_timeout(1200)
                        deleted += 1
                    else:
                        break
                except Exception:
                    break

            log(f"   ✅ dihapus: {deleted}")
            return True
        finally:
            try:
                await context.close()
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════
#  FETCH OTP (headless)
# ═══════════════════════════════════════════════════════════
async def fetch_otp_headless(cfg, view=None):
    from playwright.async_api import async_playwright

    label = cfg["label"]
    profile = get_session_dir(label)
    mode = CFG.get("otpMode", "headless").lower()
    log(f"📬 scan OTP (mode={mode})...")

    async with async_playwright() as p:
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-first-run", "--no-default-browser-check",
        ]
        if mode == "offscreen":
            launch_args.extend(["--window-position=-2400,-2400", "--window-size=1280,800"])
        elif mode == "minimized":
            launch_args.extend(["--start-minimized", "--window-size=1280,800"])
        else:
            launch_args.append("--window-size=1280,800")

        context = await p.chromium.launch_persistent_context(
            user_data_dir=profile,
            headless=(mode == "headless"),
            args=launch_args,
            viewport={"width": 1280, "height": 800},
            locale="en-US", timezone_id="Asia/Jakarta",
        )
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto("https://mail.google.com/mail/u/0/#inbox",
                            wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(5000)

            if "mail.google.com/mail" not in page.url:
                return None

            return await _scan_otp(page, view)
        finally:
            try:
                await context.close()
            except Exception:
                pass


async def _scan_otp(page, view=None):
    started_at = time.time()
    poll = CFG.get("otpPollIntervalSec", 5)
    max_wait = CFG.get("otpTimeoutSec", 180)
    attempt = 0

    while time.time() - started_at < max_wait:
        attempt += 1
        try:
            await page.reload(wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)
        except Exception:
            pass

        rows = []
        try:
            rows = await page.query_selector_all("tr.zA")
        except Exception:
            rows = []

        log(f"   attempt {attempt}: {len(rows)} rows")

        for row in rows[:5]:
            try:
                sender_el = await row.query_selector(".yX.xY .yP, .zF")
                subj_el = await row.query_selector(".y6 span")
                sender = (await sender_el.inner_text()).strip() if sender_el else ""
                subject = (await subj_el.inner_text()).strip() if subj_el else ""
                s_low = sender.lower()
                subj_low = subject.lower()

                if "sible" not in s_low and "sible" not in subj_low:
                    continue
                if any(x in subj_low for x in ("reset", "password", "welcome")):
                    continue
                if not ("verification" in subj_low or "code" in subj_low or "otp" in subj_low):
                    continue

                log(f"   ✅ email: {subject[:50]}")
                await row.click()
                await page.wait_for_timeout(3000)

                body = ""
                for sel in ["div.a3s", ".a3s.aXjCH", "div.a3s.aiL"]:
                    body_el = await page.query_selector(sel)
                    if body_el:
                        body = await body_el.inner_text()
                        if body:
                            break

                m = re.search(r"\b(\d{6})\b", body)
                if not m:
                    m = re.search(r"\b(\d{6})\b", subject)
                if m:
                    code = m.group(1)
                    log(f"   ✅ OTP = {code}")
                    return code

                try:
                    await page.go_back()
                    await page.wait_for_timeout(2000)
                except Exception:
                    pass
            except Exception as e:
                log(f"   ⚠️ row error: {e}")
                continue

        await sleep_sec(poll)

    return None


# ═══════════════════════════════════════════════════════════
#  LOGIN ONE
# ═══════════════════════════════════════════════════════════
async def login_one(cfg, view=None):
    label = cfg["label"]
    email = cfg["email"]
    password = cfg["siblePassword"]

    log(f"🔐 {label} ({email})")
    ua = random_ua()

    # ═══════════════════════════════════════════════════════
    #  STEP 0: cek session — kalau belum ada, setup Google dulu
    # ═══════════════════════════════════════════════════════
    if not has_session(label):
        log(f"⚠️ session {label} belum ada → setup Google (mode NORMAL)")
        set_status(view, "🔐", "blue", "Google setup", "(popup)")
        ok = await setup_google_session(cfg, view)
        if not ok:
            set_status(view, "❌", "red", "Google setup failed")
            return None

    # ═══════════════════════════════════════════════════════
    #  STEP 1: PURGE dulu (hapus email Sible lama)
    # ═══════════════════════════════════════════════════════
    if CFG.get("deleteOldSibleEmails", True):
        set_status(view, "🗑️", "yellow", "purging old emails")
        log(f"🗑️ purge email lama dulu...")
        await purge_old_sible_emails(cfg, view)

    # ═══════════════════════════════════════════════════════
    #  STEP 2: POST /auth/login (Sible kirim OTP baru)
    # ═══════════════════════════════════════════════════════
    set_status(view, "🔐", "blue", "login Sible")
    log(f"🔐 POST /auth/login (minta OTP baru)...")
    try:
        login_resp = await raw("/auth/login", method="POST",
                               body={"identifier": email, "password": password},
                               headers_extra={"user-agent": ua})
    except RuntimeError as e:
        set_status(view, "❌", "red", "login failed", str(e)[:40])
        log(f"❌ login: {e}")
        return None

    if not (login_resp.get("data") or {}).get("needsOtp"):
        set_status(view, "⚠️", "yellow", "unexpected response")
        return None

    otp_email = login_resp["data"].get("email") or email
    log(f"📧 OTP → {otp_email}")

    # ═══════════════════════════════════════════════════════
    #  STEP 3: baca OTP baru (headless)
    # ═══════════════════════════════════════════════════════
    set_status(view, "📬", "yellow", "reading OTP")
    log(f"📬 scan OTP baru...")
    try:
        code = await fetch_otp_headless(cfg, view)
    except Exception as e:
        set_status(view, "❌", "red", "OTP failed", str(e)[:40])
        log(f"❌ OTP failed: {e}")
        return None

    if not code:
        set_status(view, "❌", "red", "OTP not found")
        return None

    log(f"✅ OTP: {code}")

    # ─── 4. verify OTP ───
    set_status(view, "🔐", "blue", "verifying OTP")
    try:
        verify_resp = await raw("/auth/verify-otp", method="POST",
                                body={"email": otp_email, "code": code, "purpose": "login"},
                                headers_extra={"user-agent": ua})
    except RuntimeError as e:
        set_status(view, "❌", "red", "verify failed", str(e)[:40])
        log(f"❌ verify: {e}")
        return None

    d = verify_resp.get("data") or {}
    if not d.get("accessToken"):
        set_status(view, "❌", "red", "no token")
        return None

    username = d["user"]["username"]
    balance = d["user"].get("balance", 0)
    log(f"✅ {username}  bal={balance}")
    if view:
        view.username = username
        view.balance = balance
        set_status(view, "✅", "green", "logged in", username)

    return {
        "label": label, "identifier": email,
        "email": d["user"]["email"], "username": username,
        "userId": d["user"]["id"],
        "accessToken": d["accessToken"],
        "refreshToken": d.get("refreshToken", ""),
        "savedAt": datetime.now(timezone.utc).isoformat(),
        "refreshedAt": datetime.now(timezone.utc).isoformat(),
        "user": d["user"],
    }


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
        await sleep_sec(rand_int(600, 1800) / 1000)

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
            await sleep_sec(wait_ms / 1000)
            if not LOOP:
                break
        except Exception as e:
            set_status(view, "❌", "red", "error", str(e)[:40])
            log(f"[{account.get('label')}] ❌ {e}")
            await notify_webhook(f"❌ **{account.get('label')}** {e}")
            await sleep_sec(60)


# ═══════════════════════════════════════════════════════════
#  MODE --add
# ═══════════════════════════════════════════════════════════
async def amain_add(label):
    init_log()
    console = Console()

    try:
        account_cfg = load_accounts(ACCOUNTS_FILE)
    except Exception as e:
        console.print(f"[red]❌ {e}[/red]")
        sys.exit(1)

    cfg = None
    for a in account_cfg:
        if a["label"] == label:
            cfg = a
            break

    if not cfg:
        console.print(f"[red]❌ label '{label}' tidak ditemukan[/red]")
        console.print(f"[yellow]Tersedia:[/yellow]")
        for a in account_cfg:
            console.print(f"  - {a['label']}")
        sys.exit(1)

    view = AccountView(cfg["label"], cfg["email"])
    ok = await setup_google_session(cfg, view)

    if ok:
        console.print()
        console.print(f"[green]✅ Session tersimpan[/green]")
        console.print(f"[green]✅ Jalankan: python sible.py --only={label}[/green]")
    else:
        console.print(f"[red]❌ Setup gagal[/red]")
        sys.exit(1)


# ═══════════════════════════════════════════════════════════
#  RESET SESSION
# ═══════════════════════════════════════════════════════════
def do_reset_session(label=None):
    import shutil
    try:
        account_cfg = load_accounts(ACCOUNTS_FILE)
    except Exception:
        account_cfg = []

    targets = [label] if label else [a["label"] for a in account_cfg]

    for lb in targets:
        d = get_session_dir(lb)
        if os.path.exists(d):
            try:
                shutil.rmtree(d, ignore_errors=False)
            except Exception:
                shutil.rmtree(d, ignore_errors=True)
            if os.path.exists(d):
                print(f"❌ {d} masih ada (locked)")
            else:
                print(f"🗑️  removed {d}")
        else:
            print(f"ℹ️  {d} not found")


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
        if RESET_SESSION:
            do_reset_session(ADD_LABEL)
            return
        if ADD_LABEL:
            asyncio.run(amain_add(ADD_LABEL))
            return
        asyncio.run(amain())
    except KeyboardInterrupt:
        pass
    finally:
        close_log()


if __name__ == "__main__":
    main()
