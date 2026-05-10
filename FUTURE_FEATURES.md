# MYMINI3D Laser Studio — Future Feature Ideas

---

## Feature 1 — Encrypted Multi-Factory Product Sync

### Overview
A walkie-talkie style data sync system across multiple factory installations.
Any factory can push their product list to GitHub. All other factories are
notified within the hour and can sync to the latest master list.
All data is AES-encrypted so the source code on GitHub is useless without
the official compiled `.exe`.

---

### Part 1 — Encryption

**Goal:** Product names, folder paths, and all synced data are encrypted.
The decryption key is baked into the compiled `.exe` at build time.
Anyone who clones the source code from GitHub cannot read the data.
Only machines running the official installer can encrypt or decrypt.

**How it works:**
- A secret key is generated once and stored in `.build_secrets` on the
  developer's PC (gitignored, never pushed to GitHub)
- `build.ps1` reads the key and injects it into the exe via PyInstaller
- `app/core/crypto.py` provides `encrypt(data)` and `decrypt(data)`
  using AES-256 (Python `cryptography` library, already in requirements)
- Running from source = key is `"NO_KEY"` = data unreadable
- Running official `.exe` = real key baked in = works normally

**`.build_secrets` file (gitignored):**
```
MYMINI3D_ENCRYPT_KEY=<random 32-byte AES key, generated once>
MYMINI3D_GITHUB_TOKEN=<GitHub PAT with repo scope>
```

---

### Part 2 — GitHub Data Storage

Same repo (`Dksoon/MYMINI3D-Laser-Studio`), new folder:

```
data/
├── manifest.json      ← plain JSON, readable by app to check version
└── products.enc       ← AES-encrypted full product list
```

**`manifest.json` structure:**
```json
{
  "data_version": "0.3",
  "pushed_at": "2026-05-11 10:32:03",
  "product_count": 91,
  "description": "Added TARMAC XGT V2, NEW KAIDO, BIG TRUCK"
}
```

**`products.enc`:**
- AES-encrypted JSON of the entire product list
- Unreadable without the official `.exe`

---

### Part 3 — Hourly Background Check

Every 60 minutes, a silent background thread:
1. Fetches `data/manifest.json` from GitHub (no token needed, public file)
2. Reads `data_version` field (e.g. `"0.3"`)
3. Compares with locally stored `last_seen_data_version` (e.g. `"0.2"`)
4. If same → silent, sleep another hour
5. If newer → trigger sync popup on main thread

**Popup shown once per new version:**
```
┌──────────────────────────────────────────────┐
│  📦  New Product Data Available              │
│                                              │
│  Version   :  0.3                            │
│  Pushed    :  2026-05-11  10:32 PM           │
│  Products  :  91  (you currently have 88)    │
│  Changes   :  "Added TARMAC XGT V2,          │
│               NEW KAIDO, BIG TRUCK"          │
│                                              │
│  [  Skip  ]              [  ✓ Sync Now  ]    │
└──────────────────────────────────────────────┘
```

- **Skip** → saves `last_seen_data_version = "0.3"` → never asks about
  v0.3 again, even on restart
- **Sync Now** → downloads, decrypts, replaces product list → saves version

---

### Part 4 — Push Flow (any factory)

Any factory running the official `.exe` can push. The GitHub token is
baked into the exe at build time — no setup needed on factory machines.

**New UI — Settings → Data → "Shared Product Sync" section:**
```
┌──────────────────────────────────────────────┐
│  SHARED PRODUCT SYNC                         │
│                                              │
│  Current data version  :  v0.3              │
│  Last synced           :  2026-05-11 10:35  │
│  Products in master    :  91                 │
│                                              │
│  Description of changes:                     │
│  [ What's new in this push?... ]             │
│                                              │
│  [ 📥 Sync Now ]    [ 📤 Push My Products ] │
└──────────────────────────────────────────────┘
```

**Push sequence:**
1. Read all products from local SQLite database
2. Convert to JSON
3. Encrypt with AES key (baked into exe)
4. Fetch current manifest → read version (e.g. `"0.3"`)
5. Auto-bump to next version (`"0.4"`)
6. Upload `products.enc` to GitHub using token baked into exe
7. Upload `manifest.json` with new version + description + timestamp
8. Show confirmation: `"✓ Pushed v0.4 — 91 products uploaded"`
9. All other factories notified within the hour

---

### Part 5 — Sync Strategy (Replace, not Merge)

Walkie-talkie model: you hear exactly what was said.

When any factory syncs:
- Downloads `products.enc` from GitHub
- Decrypts it using key baked into exe
- **Replaces** their entire local product list with the master list
- Saves `last_seen_data_version` to config
- Shows: `"✓ Synced — 91 products loaded"`

No merge, no conflict. Last push = master. Clean and predictable.

---

### Part 6 — Sequential Push Handling

There are no real conflicts. GitHub processes one API call at a time.
If two factories push within seconds of each other:

```
10:32:00 PM  Factory 1 pushes → master becomes v0.3 (Factory 1's list)
10:32:03 PM  Factory 2 pushes → master becomes v0.4 (Factory 2's list)

Result: Everyone syncs to v0.4. Correct. ✓
```

Last push always wins. Every push gets a unique timestamp and version number.

---

### Part 7 — Version Numbering

| Type         | Example          | Stored where                      |
|--------------|------------------|-----------------------------------|
| App version  | `2.0.8`          | `app/__init__.py`                 |
| Data version | `0.1` `0.2` `0.3`| `data/manifest.json` on GitHub    |

Completely independent. App update = new exe. Data update = new product list.
Both check every hour automatically.

---

### Part 8 — Files to Create / Change

| File                              | What changes                                      |
|-----------------------------------|---------------------------------------------------|
| `.build_secrets`                  | New — encryption key + GitHub token (gitignored)  |
| `app/core/crypto.py`              | New — encrypt/decrypt using baked-in AES key      |
| `app/core/data_sync.py`           | New — push/pull product data to/from GitHub       |
| `app/core/config.py`              | Add `last_seen_data_version` to defaults          |
| `app/ui/pages/settings_page.py`   | Add Shared Sync section to Data tab               |
| `app/ui/main_window.py`           | Start hourly background check on launch           |
| `build.ps1`                       | Inject key + token from `.build_secrets` into exe |
| `.gitignore`                      | Add `.build_secrets` explicit entry               |
| `data/manifest.json`              | New in repo — starts at v0.1                      |
| `data/products.enc`               | New in repo — populated on first push             |

---

### Estimated Complexity

| Area              | Effort  | Notes                                         |
|-------------------|---------|-----------------------------------------------|
| Encryption        | Medium  | `cryptography` lib already in requirements    |
| GitHub push/pull  | Medium  | Same API pattern as existing update_service   |
| Hourly checker    | Low     | QTimer pattern already used in app            |
| Settings UI       | Low     | Follows existing Data tab pattern             |
| Build integration | Medium  | New `.build_secrets` injection in build.ps1   |
| **Total**         | **~1 session** | **Buildable in one go when ready**      |

---

*Documented: 2026-05-11*
*Status: Planned — not yet built*
