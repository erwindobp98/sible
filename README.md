# ⛏️ Sible Mining Runner

Bot otomasi mining **Sible Network** dengan **Chromium OTP**. Support multi-akun, setup manual sekali, running headless 24/7.

---

## 🎯 Fitur

- ✅ **Setup akun manual sekali** — Chromium popup, auto-isi email+password Google, tunggu user selesaikan consent
- ✅ **Session persistence** — Chromium profile per akun (folder `sessions/{label}/`)
- ✅ **Headless mode** — running di background setelah setup
- ✅ **Purge email lama** — hapus email Sible lama sebelum minta OTP baru
- ✅ **Auto-OTP** — baca OTP dari Gmail via Chromium
- ✅ **Multi-akun** — concurrent, masing-masing punya task sendiri
- ✅ **Auto relogin** — kalau token JWT expired
- ✅ **Auto claim** — claim reward otomatis
- ✅ **Adaptive wake** — tidur sesuai `nextAdAt` / `endsAt`
- ✅ **Dashboard Rich** — panel per akun, status real-time
- ✅ **CSV log** — history mining di `mining-log.csv`
- ✅ **Discord webhook** — notifikasi claim (opsional)
- ✅ **Auto referral** — apply kode referral (opsional)

---

## 📁 Struktur File

```
sible/
├── sible.py                 # Main script
├── config.json              # Config (auto-generate)
├── accounts.json            # Daftar akun (auto-generate)
├── accounts-auth.json       # Token JWT (auto-generate)
├── mining-log.csv           # History (auto-generate)
├── README.md                # Dokumen ini
├── sessions/                # Chromium profile per akun (auto)
│   ├── akun1/
│   ├── akun2/
│   └── akun3/
└── debug/
    └── run.log              # Log lengkap (auto)
```

---

## 📦 Instalasi

### Requirement

- **Python 3.10+** ([download](https://python.org))
- **Chromium** (via Playwright)
- **OS**: Windows / Linux / macOS

## 🚀 Instalasi

### 1. Clone Repository

```bash
git clone https://github.com/erwindobp98/sible.git
cd sible
```

### 2. Install Dependencies

**Isi `requirements.txt`:**

```txt
httpx>=0.27.0
rich>=13.7.0
patchright>=1.0.0
```

```bash
pip install -r requirements.txt
```

### 3. Install Chromium untuk Patchright

```bash
python -m patchright install chromium
```

**Kalau gagal**, pakai fallback playwright:

```bash
python -m playwright install chromium
```

**Kalau di Linux (server tanpa GUI):**
```bash
playwright install --with-deps chromium
```

### 4. Verify

```bash
python -c "import httpx, rich, playwright; print('OK')"
```

---

## 📝 Persiapan

### 1. Generate Config & Accounts

Pertama kali jalan, script akan **auto-generate** `config.json` dan `accounts.json`:

```bash
python sible.py
```

Output:
```
📝 Generated config.json — edit dulu lalu jalankan ulang.
📝 Generated accounts.json — isi akun, lalu jalankan ulang.
```

### 2. Edit `accounts.json`

```json
{
    "accounts": [
        {
            "label": "akun1",
            "email": "akun1@gmail.com",
            "siblePassword": "PASSWORD_SIBLE_KAMU",
            "gmailPassword": "PASSWORD_GMAIL_KAMU"
        },
        {
            "label": "akun2",
            "email": "akun2@gmail.com",
            "siblePassword": "PASSWORD_SIBLE_YANIZ",
            "gmailPassword": "PASSWORD_GMAIL_YANIZ"
        }
    ]
}
```

**Field:**
| Field | Isi |
|---|---|
| `label` | Nama panggilan (unik) |
| `email` | Email Google (Sible & Gmail sama) |
| `siblePassword` | Password login **Sible** |
| `gmailPassword` | Password login **Gmail** (untuk Chromium) |

### 3. Edit `config.json` (Opsional)

```json
{
    "referralCode": "",
    "interval": 3600,
    "jitterSec": 3,
    "minDelayBetweenAccountsSec": 2,
    "maxDelayBetweenAccountsSec": 6,
    "rateLimitBackoffSec": 30,
    "refreshEndpoint": "/auth/refresh",
    "autoRelogin": true,
    "reloginOn401": true,
    "logCsv": true,
    "csvFile": "mining-log.csv",
    "discordWebhook": "",
    "quiet": false,
    "debugRefresh": true,

    "setupMode": "normal",
    "purgeMode": "headless",
    "otpMode": "headless",

    "setupTimeoutSec": 1800,
    "otpTimeoutSec": 180,
    "otpPollIntervalSec": 5,
    "sessionsDir": "sessions",
    "deleteOldSibleEmails": true
}
```

**Penjelasan config penting:**

| Field | Default | Fungsi |
|---|---|---|
| `referralCode` | `""` | Kode referral (kosong = tidak apply) |
| `interval` | `3600` | Max interval antar cycle (detik) |
| `discordWebhook` | `""` | URL webhook Discord (kosong = off) |
| `setupMode` | `"normal"` | Mode Chromium saat `--add` |
| `purgeMode` | `"headless"` | Mode Chromium saat hapus email lama |
| `otpMode` | `"headless"` | Mode Chromium saat baca OTP |
| `setupTimeoutSec` | `1800` | Max tunggu user selesai setup (30 menit) |
| `otpTimeoutSec` | `180` | Max tunggu OTP masuk (3 menit) |
| `otpPollIntervalSec` | `5` | Interval cek email (detik) |
| `deleteOldSibleEmails` | `true` | Hapus email lama sebelum minta OTP |

**Mode Chromium:** `"normal"`, `"headless"`, `"minimized"`, `"offscreen"`.

---

## 🚀 Cara Pakai

### 1. Setup Akun Baru (`--add`)

**Pertama kali**, setup tiap akun (nama akun sesuai isi config):

```bash
python sible.py --add=akun1
```

**Yang terjadi:**
1. Chromium **popup muncul**
2. Script **auto-isi email + password** Google
3. **Kamu selesaikan manual** — consent screen (recovery email, phone, address), 2FA, dll
4. Setelah sampai inbox → **TUTUP BROWSER manual**
5. Script **deteksi close** → simpan session
6. Session tersimpan di `sessions/akun1/`

**Log yang diharapkan:**
```
🔐 SETUP GOOGLE SESSION — akun1
🌐 goto Gmail...
📧 auto-isi email: akun1@gmail.com
✅ email diisi
🔑 auto-isi password
✅ password diisi — silakan lanjutkan manual
⏳ TUNGGU USER:
   - Selesaikan login/consent di browser
   - CLOSE BROWSER manual kalau sudah di inbox
[KAMU CLOSE BROWSER]
🍪 Chromium closed
✅ Session tersimpan
✅ Jalankan: python sible.py --only=akun1
```

### 2. Jalankan Mining

**Test 1 akun dulu:**
```bash
python sible.py --only=akun1
```

**Kalau berhasil, jalankan semua:**
```bash
python sible.py
```

**Log yang diharapkan:**
```
🔐 nanikz (akun1@gmail.com)
🗑️ purge email lama dulu...
   ✅ dihapus: 2
🔐 POST /auth/login (minta OTP baru)...
📧 OTP → itsnanikz081@gmail.com
📬 scan OTP baru...
   attempt 1: 1 rows
   ✅ email: Sible Network — Your sign-in code
   ✅ OTP = 765109
✅ OTP: 765109
✅ nanikz  bal=10.8
🚀 session started
💰 claimed 0.80 → 12.08
```

### 3. Biarkan Jalan

- **Dashboard Rich** muncul dengan panel per akun
- Biarkan terminal terbuka
- Ctrl+C untuk stop

### 4. Reset Session (Kalau Perlu)

**Reset 1 akun:**
```bash
python sible.py --reset-session --add=akun1
```

**Reset semua:**
```bash
python sible.py --reset-session
```

---

## 🔧 Alur Kerja

### Setup (`--add`)

```
1. Buka Chromium (mode setupMode)
2. Auto-isi email + password Google
3. TUNGGU user selesaikan consent manual
4. TUNGGU user close browser manual
5. Simpan session
```

### Run Normal

```
1. Cek session — kalau belum ada, setup dulu
2. PURGE email Sible lama (headless)
3. POST /auth/login → Sible kirim OTP baru
4. Scan OTP baru (headless)
5. POST /auth/verify-otp → token
6. Mining: start session, nonton ads, claim reward
7. Adaptive wake → ulang
```

### Relogin (Token Expired)

Otomatis — sama seperti Run Normal (purge → login → OTP → verify).

---

## 📖 Command Reference

```bash
# Setup akun baru (manual + popup)
python sible.py --add=nanikz

# Reset session 1 akun (harus pakai --add)
python sible.py --reset-session --add=akun1

# Reset semua session
python sible.py --reset-session

# Jalankan 1 akun
python sible.py --only=akun1

# Exclude 1 akun
python sible.py --exclude=akun1

# Jalankan semua akun
python sible.py

# Sekali saja (tidak loop)
python sible.py --once

# Custom interval (detik)
python sible.py --interval=1800

# Custom config & accounts file
python sible.py --config=myconfig.json --accounts=myaccounts.json
```

**Cek log real-time:**
```bash
tail -f debug/run.log          # Linux/Mac
Get-Content debug/run.log -Wait # Windows PowerShell
```

---

## 🔧 File Konfigurasi

### `accounts.json`

```json
{
    "accounts": [
        {
            "label": "akun1",
            "email": "akun1@gmail.com",
            "siblePassword": "PASSWORD_SIBLE",
            "gmailPassword": "PASSWORD_GMAIL"
        }
    ]
}
```

### `accounts-auth.json` (auto)

```json
{
    "createdAt": "2026-10-09T09:00:00.000Z",
    "accounts": [
        {
            "label": "akun1",
            "identifier": "akun1@gmail.com",
            "email": "akun1@gmail.com",
            "username": "akun1",
            "userId": "...",
            "accessToken": "eyJ...",
            "refreshToken": "eyJ...",
            "savedAt": "...",
            "refreshedAt": "...",
            "user": { ... }
        }
    ]
}
```

### `mining-log.csv` (auto)

```csv
timestamp,label,username,balance,accumulated,rate,ads,boost,claimed,session,running
2026-10-09T09:35:46.000Z,akun1,akun1,12.08,0.8,0.16,3/3,60,0.8,running,1
```

---

## 🐛 Troubleshooting

### 1. Login Google Gagal — Consent Screen

**Gejala:** Chromium stuck di halaman "Add recovery email" / "Verify it's you".

**Solusi:**
- **Mode `--add`** → kamu **handle manual** consent screen
- Setelah di inbox → **close browser manual**
- Script deteksi close → simpan session

### 2. OTP Invalid / Salah Ambil

**Gejala:** `verify failed: HTTP 400 OTP_INVALID`

**Penyebab:** Purge tidak jalan / email lama masih ada.

**Solusi:**
- Cek `deleteOldSibleEmails: true` di config
- Kalau masih gagal → manual hapus email di Gmail
- Jalankan ulang

### 3. Chromium Hang / Tidak Close

**Gejala:** Chromium stuck > 30 menit.

**Solusi:**
- Ganti `setupMode` / `purgeMode` / `otpMode` ke `"offscreen"` atau `"normal"`
- Kalau tetap → kill Chromium manual
- `python sible.py --reset-session --add=label`

### 4. Token Expired Terus

**Gejala:** Relogin berkali-kali.

**Solusi:**
- Cek koneksi internet
- Cek jam sistem (harus akurat)
- Cek `reloginOn401: true` di config

### 5. Session Folder Corrupt

**Gejala:** Error saat launch Chromium.

**Solusi:**
- `python sible.py --reset-session --add=label`
- Setup ulang

### 6. Rate Limit (HTTP 429)

**Gejala:** `HTTP 429 rate-limited`

**Solusi:**
- Tunggu `rateLimitBackoffSec` (default 30s)
- Naikkan `minDelayBetweenAccountsSec` & `maxDelayBetweenAccountsSec` di config
- Kurangi jumlah akun concurrent

---

## 💡 Tips 24/7

### Windows — Task Scheduler

1. Buka **Task Scheduler** → **Create Task**
2. **Trigger**: At startup
3. **Action**: 
   - Program: `python`
   - Arguments: `sible.py`
   - Start in: `C:\path\to\sible`
4. Save

### Linux/Mac — nohup

```bash
cd /path/to/sible
nohup python3 sible.py > /dev/null 2>&1 &
```

### VPS — screen

```bash
screen -S sible
python3 sible.py
# Ctrl+A, D → detach
# screen -r sible → reattach
```

### VPS — systemd service

**`/etc/systemd/system/sible.service`:**
```ini
[Unit]
Description=Sible Mining Runner
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/home/your_user/sible
ExecStart=/usr/bin/python3 sible.py
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable sible
sudo systemctl start sible
sudo systemctl status sible
```

---

## ❓ FAQ

### Q: Kenapa harus `--add` manual? Tidak bisa otomatis?

**A:** Google punya consent screen (recovery email, phone, address), captcha, dan 2FA yang **tidak bisa di-handle otomatis** tanpa user intervensi. Sekali setup, berikutnya headless.

### Q: Apakah perlu Gmail App Password?

**A:** **Tidak.** Script pakai Chromium untuk login Gmail, jadi cukup password Gmail biasa.

### Q: Berapa akun maksimal?

**A:** **Tidak ada batas** — tapi pertimbangkan:
- 1 akun = 1 folder Chromium (~100-200 MB)
- Login concurrent berat → naikkan delay antar akun
- Saran: 5-20 akun per instance

### Q: Bisa di VPS tanpa GUI?

**A:** **Bisa** — asal session sudah ada (setup di lokal dengan GUI dulu, copy folder `sessions/` + `accounts.json` ke VPS).

Atau setup via VNC/RDP sekali.

### Q: Chromium buka terus, boros?

**A:** Setelah setup, semua **headless** — Chromium jalan di background, tidak muncul popup.

### Q: Kenapa `--add` auto-isi tapi tidak auto-submit?

**A:** Auto-submit bisa trigger Google "suspicious activity". Biar natural, **user submit manual** setelah password.

### Q: Session expired berapa lama?

**A:** Chromium session Google biasanya ~30-90 hari. Kalau expired → setup ulang `--reset-session --add=label`.

### Q: Bisa pakai email Sible (bukan Gmail)?

**A:** Kalau email Sible = email Sible (bukan Google), **tidak bisa** pakai script ini (karena login via Google). Harus Google account.

### Q: Discord webhook — format URL?

**A:** 
```
https://discord.com/api/webhooks/{webhook_id}/{webhook_token}
```
Dapatkan dari: **Discord → Server Settings → Integrations → Webhooks → New Webhook**.

### Q: Ada notifikasi lain selain Discord?

**A:** Belum. Bisa ditambahkan (Telegram, Slack, dll). Kirim permintaan.

---

## 🙏 Kredit

- **Sible Network** — platform mining
- **Playwright** — browser automation
- **Rich** — dashboard terminal
- **httpx** — async HTTP client

---

**Selamat mining! ⛏️🚀**
