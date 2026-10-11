# ⛏️ Sible Mining Runner

Bot auto-mining untuk [Sible Network](https://mine.sible.network) dengan auto-login OTP via Gmail (IMAP), multi-akun, auto-claim, dan dashboard live berbasis Rich.

---

## ✨ Fitur

- 🤖 **Auto-mining** — start session, watch ads, claim reward otomatis
- 📧 **Auto-login OTP** — baca kode verifikasi langsung dari Gmail via IMAP (tanpa browser)
- 👥 **Multi-akun** — jalankan banyak akun sekaligus (concurrent)
- 🎯 **Auto-claim** — klaim reward begitu `canClaim = true`
- 🔁 **Auto-refresh & auto-relogin** — token expired ditangani otomatis
- 📊 **Live Dashboard** — pantau balance, rate, ads, boost, status per akun real-time
- 📝 **CSV Logging** — riwayat mining tersimpan di `mining-log.csv`
- 🔔 **Discord Webhook** — notifikasi claim & error (opsional)
- 🌐 **Random UA / Fingerprint** — headers realistis, hindari deteksi
- ⚡ **Early Return IMAP** — stop scan begitu OTP valid ditemukan
- 🛡️ **Rate-limit guard** — backoff otomatis saat kena HTTP 429

---

## 📁 Struktur Project

```
sible/
├── sible.py                  # main script
├── .gitignore
├── README.md
│
├── config.json               # auto-generate saat pertama run
├── accounts.json             # auto-generate saat pertama run
├── accounts-auth.json        # token store (JANGAN di-share!)
├── mining-log.csv            # auto-generate
└── debug/
    └── run.log               # auto-generate
```

---

## 🚀 Instalasi

### 1. Clone Repository

```bash
git clone https://github.com/erwindobp98/sible.git
cd sible
```

### 2. Install Dependencies

Butuh **Python 3.9+**

```bash
pip install httpx rich
```

### 3. Generate Config

Jalankan sekali, script otomatis membuat `config.json` & `accounts.json`:

```bash
python sible.py
```

---

## ⚙️ Konfigurasi

### `config.json`

Field di bawah ini **persis sama** dengan `DEFAULTS` di dalam `sible.py`:

```json
{
    "referralCode": "ween",
    "interval": 28920,
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

    "imapHost": "imap.gmail.com",
    "imapPort": 993,
    "otpTimeoutSec": 120,
    "otpPollIntervalSec": 3,
    "otpMaxAgeSec": 300,
    "otpSinceToleranceSec": 120,

    "earlyReturnSec": 60,

    "loginMaxRetry": 2,
    "loginRetryDelaySec": 10
}
```

| Field | Deskripsi |
|-------|-----------|
| `referralCode` | Kode referral (opsional, di-apply otomatis) |
| `interval` | Interval default antar cycle (detik) — default 28920 |
| `jitterSec` | Jitter random untuk hindari pola |
| `minDelayBetweenAccountsSec` / `maxDelayBetweenAccountsSec` | Delay antar akun |
| `rateLimitBackoffSec` | Waktu tunggu saat kena HTTP 429 |
| `refreshEndpoint` | Endpoint refresh token |
| `autoRelogin` | Auto-relogin kalau refresh gagal |
| `reloginOn401` | Relogin kalau kena HTTP 401 |
| `logCsv` | Aktifkan logging ke CSV |
| `csvFile` | Nama file CSV output |
| `discordWebhook` | URL webhook Discord (kosongkan jika tidak pakai) |
| `quiet` | Matikan log ke stdout |
| `debugRefresh` | Log detail refresh token |
| `imapHost` / `imapPort` | Server IMAP Gmail |
| `otpTimeoutSec` | Timeout tunggu OTP (detik) |
| `otpPollIntervalSec` | Interval poll IMAP |
| `otpMaxAgeSec` | Batas umur email OTP yang dianggap valid |
| `otpSinceToleranceSec` | Toleransi timestamp saat search email |
| `earlyReturnSec` | Kalau email < N detik → stop scan langsung |
| `loginMaxRetry` | Jumlah percobaan login |
| `loginRetryDelaySec` | Delay antar retry login |

---

## 📧 Setup Gmail App Password (WAJIB)

Bot butuh akses IMAP ke Gmail untuk baca kode OTP. **Password biasa tidak bisa** — harus pakai **App Password**.

### Langkah:

1. **Aktifkan 2-Step Verification**:
   👉 https://myaccount.google.com/security

2. **Buat App Password**:
   👉 https://myaccount.google.com/apppasswords

3. Pilih:
   - App: **Mail**
   - Device: **Other** → ketik `Sible Bot`

4. Copy **16 karakter** yang muncul (contoh: `abcdefghijklmnop`)

5. **Aktifkan IMAP** di Gmail:
   👉 Gmail → ⚙️ Settings → **Forwarding and POP/IMAP** → **Enable IMAP**

> ⚠️ App Password hanya muncul **sekali**. Simpan di tempat aman.

---

## 👤 Konfigurasi Akun

Edit `accounts.json` (dibuat otomatis saat pertama run). Formatnya **disesuaikan dengan `load_accounts()` di script**:

```json
{
    "accounts": [
        {
            "label": "akun1",
            "email": "akun1@gmail.com",
            "siblePassword": "PASSWORD_SIBLE_KAMU",
            "gmailAppPassword": "abcdefghijklmnop"
        }
    ]
}
```

| Field | Deskripsi | Wajib |
|-------|-----------|:-----:|
| `label` | Nama bebas untuk identifikasi | ✅ |
| `email` | Email akun Sible **dan** Gmail (harus sama) | ✅ |
| `siblePassword` | Password akun Sible | ✅ |
| `gmailAppPassword` | 16 karakter App Password Gmail (tanpa spasi) | ✅ |

**Alias yang juga diterima** (dari script):

- `email` bisa juga ditulis `sibleEmail` atau `identifier`
- `siblePassword` bisa juga ditulis `password`
- `gmailAppPassword` bisa juga ditulis `gmailPass`

> 💡 Email Sible **harus** Gmail karena OTP dikirim ke inbox Gmail.
> ⚠️ `gmailAppPassword` **wajib tepat 16 karakter** — kalau kurang/lebih script akan error.

---

## ▶️ Cara Menjalankan

### Mode Default (loop terus-menerus)

```bash
python sible.py
```

---

## 📊 Dashboard

```
╭─────────────────── ⛏️  SIBLE MINING ───────────────────╮
│ ╭─ akun1 ──────────────────────────────── logged in ─╮ │
│ │ Status   : ✅ logged in · akun1                    │ │
│ │ Balance  : 0.00123400                              │ │
│ │ Rate/hr  : 0.00012300                              │ │
│ │ Ads      : 3/3   Boost : +6%   Run : ✓             │ │
│ │ Cycle    : 12   Next : 45s                         │ │
│ ╰────────────────────────────────────────────────────╯ │
│ ╭─ akun2 ──────────────────────────────── logged in ─╮ │
│ │ Status   : 💤 sleeping · 120s                      │ │
│ │ Balance  : 0.00098700                              │ │
│ │ Rate/hr  : 0.00010500                              │ │
│ │ Ads      : 2/3   Boost : +4%   Run : ✓             │ │
│ │ Cycle    : 8    Next : 120s                        │ │
│ ╰────────────────────────────────────────────────────╯ │
╰─────────────────────────────────────────────────────────╯
```

---

## 📝 Log & Output

### `mining-log.csv`

```
timestamp,label,username,balance,accumulated,rate,ads,boost,claimed,session,running
2024-01-15T10:30:00+00:00,akun1,user1,0.001234,0.005678,0.000123,3/3,6,0.000123,running,1
```

### `debug/run.log`

Log detail semua aktivitas termasuk scan IMAP, response API, error, dsb. Berguna untuk troubleshooting.

### `accounts-auth.json`

⚠️ **JANGAN DI-SHARE!** Berisi access token & refresh token semua akun. Kalau bocor, akun bisa diambil alih.

---

## 🐛 Troubleshooting

### ❌ `IMAP login failed`

- Pastikan **2FA aktif** di Gmail
- Pastikan pakai **App Password** (16 karakter), bukan password biasa
- Pastikan **IMAP aktif** di Gmail settings
- Kalau ganti password Google, App Password lama akan mati — buat baru

### ❌ `OTP not found`

- Cek folder inbox Gmail — email OTP mungkin masuk ke **Spam**
- Pastikan email Sible = email Gmail
- Naikkan `otpTimeoutSec` di `config.json`
- Cek `debug/run.log` untuk detail scan

### ❌ `HTTP 429 rate-limited`

Bot otomatis backoff `rateLimitBackoffSec` detik. Kalau sering kena:
- Naikkan `interval`
- Kurangi jumlah akun per-run
- Pisah jadi beberapa instance dengan `--only`

### ❌ `HTTP 401 Unauthorized`

Bot akan coba refresh token, jika gagal akan auto-relogin. Kalau terus gagal:
- Hapus `accounts-auth.json`, jalankan ulang (login fresh)
- Pastikan `siblePassword` masih benar

### ❌ Dashboard tidak muncul

- Pastikan terminal mendukung ANSI / Rich
- Jangan pakai `--quiet` kalau ingin lihat dashboard

### ❌ `gmailAppPassword harus 16 karakter`

App Password punya 16 karakter. Kalau kamu copy dari Google dengan spasi (`abcd efgh ijkl mnop`), bot akan hapus spasi otomatis. Cek jumlah karakter.

---

## 🔒 Keamanan

- ✅ `accounts.json` & `accounts-auth.json` **JANGAN** di-commit ke GitHub
- ✅ Gunakan `.gitignore`
- ✅ App Password Gmail bisa **dicabut kapan saja** di https://myaccount.google.com/apppasswords
- ✅ Bot hanya akses IMAP Gmail (read-only), tidak kirim/hapus email

---

## 📌 Tips

1. **Jalankan di VPS / screen / tmux** biar tetap hidup:
   ```bash
   screen -S sible
   python3 sible.py
   # Ctrl+A, D untuk detach
   # screen -r sible untuk re-attach
   ```

2. **Pisah akun** kalau kena rate-limit:
   ```bash
   python3 sible.py --only=akun1 &
   python3 sible.py --only=akun2 &
   ```

3. **Backup `accounts-auth.json`** — biar tidak perlu login OTP ulang tiap restart.

4. **Setup systemd service** (Linux VPS) untuk auto-start.

---

## ⚠️ Disclaimer

> Script ini dibuat untuk **keperluan edukasi & otomasi pribadi**.
>
> - Gunakan dengan **bijak** dan **sesuai ToS** Sible Network.
> - Segala risiko (ban akun, suspend, dll) ditanggung **pengguna**.
> - Author **tidak bertanggung jawab** atas penyalahgunaan.
> - **Jangan jual** script ini dalam bentuk apapun.

---

**Made with ❤️ for the Sible community**
