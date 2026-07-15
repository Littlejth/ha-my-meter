# AGENTS.md — RFMU MyAccount → Home Assistant Integration

**Goal:** Build a Home Assistant integration that reads RFMU electric-account data (balance, usage kWh, due date, alerts) from <https://myaccount.rfmu.org/>.

**Full research notes:** `RESEARCH.md` (read it first — it has the platform ID, auth flow, endpoints, and architecture).

---

## Status (as of 2026-07-14)

- [x] Platform identified: **MyMeter v10.5.1.4** (WPPI Energy SaaS), ASP.NET MVC, cookie/session auth.
- [x] Auth flow reverse-engineered: `GET /` → anti-forgery token + `MM_SID` cookie → `POST /Home/Login` (form-urlencoded, JSON response `{AjaxResults, Data}`).
- [x] **reCAPTCHA CONFIRMED server-enforced** — valid creds without a `g-recaptcha-response` token → `"Please provide a valid login captcha."` (credential check runs before captcha check).
- [x] **LOGIN SOLVED (2026-07-14):** Firefox DevTools MCP login works — scope the DOM snapshot to `#LoginContainer` to reach the `#LoginEmail`/`#LoginPassword` input UIDs (the previous truncation was the blocker). Invisible reCAPTCHA issued a token and login succeeded.
- [x] **DATA ENDPOINTS CAPTURED (2026-07-14):** `POST /Usage/Download` returns `text/csv` usage (meters, intervals, date range). Verified live via the `my-meter-api` library pattern. Dashboard JSON endpoints (`/Dashboard/ChartData`, `/Widget/LoadWidgets?Region=Usage`) and `/Alerts/Index` also confirmed. Sample CSVs saved under `research-capture/`. Full API documented in `RESEARCH.md §5`.
- [x] **GENERIC HA SCAFFOLD CREATED (2026-07-14):** `custom_components/mymeter/` is a working generic MyMeter integration (domain `mymeter`, not RFMU-specific) built from the `ha-mymeter` blueprint + the `my-meter-api` endpoint/params. Files: `manifest.json`, `const.py`, `data.py`, `entity.py`, `api.py` (async aiohttp client + `parse_usage_csv`), `coordinator.py`, `config_flow.py` (+ options flow), `sensor.py` (4 sensors), `translations/en.json`, `tests/test_api.py`. Compiles clean; `parse_usage_csv` unit-verified against the research sample. See `RESEARCH.md §6` (architecture) and the component `README.md`.
- [ ] **Open:** Billing/payment endpoints (balance, due date, last bill) not yet captured; session lifetime of `MM_SID` unknown; **reauth flow added** (`async_step_reauth`/`reauth_confirm` + `allow_redirects=False` so an expired `MM_SID` reliably triggers `ConfigEntryAuthFailed`); config flow now **auto-discovers meters** (no manual internal id).

---

## Credentials

Live RFMU account credentials are in **`./creds`** (format: `USER=...`, `PASS=...`). Do **not** paste the password into chat or commit it. Read the file at runtime when needed.

---

## How to resume (priority order)

1. **Capture billing endpoints** (remaining unknown): log in via Firefox, open **View/Pay Bill**, filter Network to XHR/widget requests, record the POST/JSON shape (likely `SelectedServiceType=23` or a `/Billing/...` / `/Widget/LoadWidgets?Region=Billing` endpoint). Document in `RESEARCH.md §5.8` and add balance/due-date/last-bill sensors.
2. **Automate meter-id discovery** in `api.py`: parse `/Dashboard/Chart` for `meterId-NNNN` to map the display account number → internal id (see `RESEARCH.md §5.5`); update `config_flow.py` to accept a display number (or auto-detect) instead of the raw internal id.
3. **Add a reauth flow** (`async_step_reauth` / `ConfigEntryAuthFailed` handling) so that when `MM_SID` expires the user is prompted to re-run the browser login and paste fresh cookies.
4. **Live end-to-end test**: install the component in a HA dev instance (or HA devcontainer), add it via the UI with the session cookies from a browser login, and confirm the 4 sensors populate.

---

## Key facts to remember

- Auth cookie: `MM_SID` (`path=/; secure; samesite=lax; httponly`). Value starts with encrypted ASP.NET prefix `CfDJ8...`.
- Anti-forgery: `__RequestVerificationToken` (hidden field + cookie) required on `POST /Home/Login`.
- All data fetches: **POST + JSON**, response shape `{ AjaxResults:[...], Data:{...} }`, `window.appPath === ''` (root-relative URLs).
- reCAPTCHA sitekey: `6LcbbJsUAAAAAHXQBPiWMaNvE9Tflw41mjYGJ3TV` (invisible).
- Auth-gated routes (302→login when unauthenticated): `/Dashboard/Index`, `/Alerts/Index`. `/Home/Login` is POST-only (405 on GET).
- MyMeter skin ID for RFMU: **1286**.

---

## Tooling notes

- **Firefox DevTools MCP** is available (`firefox_devtools_*`): navigate, snapshot, fill, click, list/capture network requests. Use it to drive the real browser for login + endpoint capture.
- **curl** is fine for non-reCAPTCHA probing (token fetch, route-status checks) — see the templates in `RESEARCH.md` Appendix A.
- Model note: the current model **cannot view screenshots/images** — rely on DOM snapshots, network-request listings, and text output, not `screenshot_page`/`screenshot_by_uid`.
