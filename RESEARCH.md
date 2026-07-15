# RFMU MyAccount — Home Assistant Integration Research

> Research compiled: 2026-07-14
> Target site: <https://myaccount.rfmu.org/>
> Researched with: Firefox DevTools MCP (DOM snapshots, network requests) + `curl` for auth-flow probing.

---

## 1. Platform Identification

| Fact | Value |
| ------ | ------- |
| Platform | **MyMeter** (utility account management portal) |
| Vendor | **WPPI Energy** (wholesale power provider) — references to `wppienergy.org` and `mymeter-skins.s3.us-west-2.amazonaws.com` |
| Utility | River Falls Municipal Utilities (RFMU), River Falls, WI |
| MyMeter skin ID | **1286** (from `mymeter-skins.s3.us-west-2.amazonaws.com/1286/...`) |
| MyMeter version | **v10.5.1.4** (footer text: "v10.5.1.4 Powered By:") |
| Web framework | **ASP.NET MVC** (Razor views, `~/` bundle refs, anti-forgery tokens) |
| Client stack | jQuery + Bootstrap + Syncfusion EJ2 (`ej2.min.js`) + Google reCAPTCHA + Google Translate widget |
| Contact page | <https://www.rfmu.org/581/Utility-Billing> (linked from footer) |

This is a **commercial, closed-source SaaS** (MyMeter). There is no public API documentation. The integration must reverse-engineer the browser's HTTP traffic.

---

## 2. Authentication Flow (the critical part)

Auth is **cookie/session based**, NOT OAuth/JWT. This is good news for a HA integration — no token refresh logic needed, just persist the session cookie.

### 2.1 Step 1 — GET the login page to obtain the anti-forgery token

```
GET https://myaccount.rfmu.org/
```

Returns HTML containing, in the login `<form class="loginForm" method="POST" action="https://myaccount.rfmu.org/Home/Login">`:

- A hidden field `__RequestVerificationToken` (ASP.NET MVC anti-forgery token)
- Sets two cookies:
  - `__RequestVerificationToken` (cookie form of the token)
  - **`MM_SID`** — MyMeter Session ID (the session cookie; value begins with the encrypted ASP.NET prefix `CfDJ8...`)

Cookie attributes observed on `MM_SID`:

```
set-cookie: MM_SID=CfDJ8...; path=/; secure; samesite=lax; httponly
```

> `httponly` → cannot be read by JS; must be stored/resent by the HTTP client. `secure` → must use HTTPS.

### 2.2 Step 2 — POST credentials to /Home/Login

```
POST https://myaccount.rfmu.org/Home/Login
Content-Type: application/x-www-form-urlencoded
```

Form fields (from `processAjax({ url:'/Home/Login', data: $('.loginMain form').serialize() })`):

| Field | Example | Notes |
| ------- | --------- | ------- |
| `__RequestVerificationToken` | `CfDJ8KYMScFqkY9...` | From Step 1 |
| `LoginEmail` | `me@example.com` | max 55 chars |
| `LoginPassword` | `********` | max 55 chars |
| `RememberMe` | `true` / `false` | checkbox |
| `ExternalLogin` | `False` | hidden, always "False" for local login |
| `TwoFactorRendered` | `False` | hidden |
| `SecretQuestionRendered` | `False` | hidden |
| `RedirectUrl` | *(empty)* | hidden |
| `g-recaptcha-response` | `<token>` | **REQUIRED — server-enforced (see §3)** |

**Verified behavior (tested via `curl`, no reCAPTCHA token sent in either case):**

Invalid credentials:

```
HTTP 200
{"AjaxResults":[],"Data":{"LoginErrorMessage":"Invalid email address or password"}}
```

Valid credentials (real account, still no token):

```
HTTP 200
{"AjaxResults":[],"Data":{"LoginErrorMessage":"Please provide a valid login captcha."}}
```

- Endpoint returns **JSON**, not an HTML redirect.
- The server checks the **password first**, then the **captcha**. A missing/invalid `g-recaptcha-response` only surfaces once credentials are correct → **reCAPTCHA is server-enforced** (corrects the earlier hypothesis).
- On failure: `Data.LoginErrorMessage` is populated.
- On success (still unverified): expect `AjaxResults` / `Data` to carry account info and the `MM_SID` cookie to become an authenticated session; the client then navigates to `Dashboard/Index`.

### 2.3 Step 3 — Use the session cookie for all data requests

After a successful login, send the persisted `MM_SID` (and `__RequestVerificationToken`) cookie on every subsequent request. The site uses the `universalCallback` / `processAjax` helper in `dist/js/BaseJs.min.js`:

```js
$.ajax({ type:"POST", dataType:"json", data:t, cache:!1,
         url:(window.appPath?window.appPath:"")+i.url, ... })
```

- `window.appPath` is `''` for this deployment (endpoints are root-relative, e.g. `/Home/...`).
- All data fetches are **POST + JSON** through `processAjax`, with the response shape `{ AjaxResults:[...], Data:{...} }`.

### 2.4 Confirmed auth-gated routes (302 → login when unauthenticated)

- `GET /Dashboard/Index` → 302 (redirects to login)
- `GET /Alerts/Index` → 302
- `GET /Home/Login` → 405 for GET (POST only) — confirms POST-only login

---

## 3. reCAPTCHA Analysis (the main blocker)

- Type: **Invisible reCAPTCHA**
- Sitekey: `6LcbbJsUAAAAAHXQBPiWMaNvE9Tflw41mjYGJ3TV`
- Wired via `<button ... data-sitekey=... data-callback=onSubmit>`
- `onSubmit(token)` validates the form, then calls `processAjax({ url:'/Home/Login', data: form.serialize() })`. The `g-recaptcha-response` token is included in `form.serialize()`.

**CONFIRMED: reCAPTCHA is server-enforced.** A `/Home/Login` POST with valid credentials but **no** `g-recaptcha-response` returns `"Please provide a valid login captcha."` (see §2.2). The earlier "not enforced" hypothesis was wrong — it was an artifact of the credential check running first.

**Implications for the integration:**

- The HA integration **cannot** log in with a bare `curl`/HTTP POST. It must obtain a valid `g-recaptcha-response` token.
- Options:
  1. **Browser automation** (Playwright/Selenium, or the Firefox DevTools MCP) to render the page, let the invisible reCAPTCHA issue a token, and submit the form. Risk: Google may flag the automated browser and either lower the token score or present an unsolvable challenge.
  2. **reCAPTCHA solving service** (2captcha/anti-captcha) — fragile, costs money, against ToS.
  3. **Reverse the token endpoint** — the invisible widget calls `https://www.google.com/recaptcha/api2/...`; replicating it is impractical.
- Unknown: whether the server checks the token's risk **score** or only its **presence/validity**. A token issued to an automated browser may still pass if only presence is checked.

---

## 4. Authenticated endpoint capture (2026-07-14)

A real browser session successfully passed the invisible reCAPTCHA and logged in. This resolves the previous DOM/input blocker. The authenticated session was confirmed by opening `/Dashboard` and `/Alerts/Index` (both returned HTTP 200 and rendered the authenticated navigation). The authenticated `MM_SID` and anti-forgery cookies were also observed on subsequent requests.

### Login and post-login bootstrap

After the login button was clicked, the site navigated through this bootstrap sequence:

- `GET /Integration/LoginActionsComplete?_=...` — HTTP 200
- `GET /Dashboard` — HTTP 200
- Multiple concurrent `POST /Integration/LoadIntegrationData` — HTTP 200

The integration POSTs had `Content-Type: application/x-www-form-urlencoded`, `X-Requested-With: XMLHttpRequest`, and referer `/Integration/LoginActions`. Each request had a form body of 191 bytes; the browser network tool did not expose the response body, so the exact action names and JSON payloads remain to be captured.

### Dashboard data requests

The Dashboard itself loads these authenticated requests (all HTTP 200):

- `GET /Dashboard/Chart`
- `GET /Dashboard/ChartData`
- `GET /Widget/LoadWidgets?Region=Usage`

These are AJAX-style GETs despite the generic `processAjax` helper commonly using POST. Responses are `text/plain; charset=utf-8`, gzip-compressed, and contain the site's `{\"AjaxResults\": [...], \"Data\": {...}}` JSON envelope. Directly opening `/Dashboard/Chart` and `/Dashboard/ChartData` in the authenticated browser rendered that JSON envelope, confirming they are useful API endpoints.

The corresponding page-specific assets discovered in the authenticated Dashboard load include:

- `/dist/js/UsageChart.min.js`
- `/dist/js/HighCharts.min.js`
- `/dist/js/Property.min.js`
- `/dist/js/Popup.min.js`

`/Usage/Index` is **not** a valid route (HTTP 404); usage is embedded in the Dashboard under the `Usage` widget/region.

### Alerts

- `GET /Alerts/Index` — HTTP 200 and rendered the Alerts page.
- The page did not produce a separate XHR in the short capture window; alert content appears server-rendered or loaded as part of the page response.

### Still to capture

The response bodies can be captured with `curl` once the browser's current `MM_SID` and `__RequestVerificationToken` cookies are copied into a Netscape cookie jar. A working capture using the current browser session produced:

- `/Dashboard/Chart` — JSON envelope whose `AjaxResults[0].Value` is the chart HTML. It contains a fresh hidden anti-forgery token and the chart form (`#chartControlForm`).
- `/Dashboard/ChartData` — JSON envelope with `Data.colors` and `Data.series`; the series contain timestamp/value pairs for monthly electricity usage (for example, `1575158400000, 422.0`).
- `/Widget/LoadWidgets?Region=Usage` — JSON envelope whose `AjaxResults` contains the Usage widget HTML.
- `/Alerts/Index` — full authenticated HTML page.

Example capture:

```bash
curl --compressed -sS -b authenticated-cookies.txt \\
  -A 'Mozilla/5.0' \\
  -H 'X-Requested-With: XMLHttpRequest' \\
  -H 'Referer: https://myaccount.rfmu.org/Dashboard' \\
  'https://myaccount.rfmu.org/Dashboard/ChartData' \\
  -o dashboard-chart-data.json
```

The previously saved `cookies.txt` was stale, causing 302 redirects. The current browser cookie values were supplied manually and verified with `curl`; all three Dashboard endpoints returned HTTP 200. Captured response files are under `research-capture/` (the raw authenticated HTML is intentionally not committed as an integration fixture yet).

The next research step is to parse the HTML embedded in `AjaxResults[].Value` to enumerate form fields, labels, and any additional billing/payment links, then replay the chart form with `curl` if historical range or meter selection parameters are needed.

## 5. The MyMeter Data API (CONFIRMED, 2026-07-14)

The single most useful endpoint was reverse-engineered from the public `my-meter-api` library (github.com/jthoward64/my-meter-api, MIT) and **verified live against RFMU**. It returns raw usage as CSV — no HTML scraping needed.

### 5.1 Endpoint

```
POST /Usage/Download
Content-Type: application/x-www-form-urlencoded
Accept: text/csv
```

Returns `200` with `Content-Type: text/csv` on success, or `400 application/problem+json` (`{"title":"Bad Request","status":400,"detail":"Insufficient meter data"}`) when the meter/interval/range combination yields nothing. A stale session returns `302` to `/` (re-auth needed).

### 5.2 Authentication

1. The caller must hold a valid `MM_SID` session cookie (plus the `__RequestVerificationToken` cookie). These are obtained by completing the browser login (reCAPTCHA) — see §3 and §6.
2. **Per request**, a fresh form token is required. Fetch it with:

   ```
   GET /Dashboard   (send MM_SID + __RequestVerificationToken cookies)
   → parse the hidden <input name="__RequestVerificationToken" value="…">
   ```

   (The form token differs from the cookie token; the library re-reads it every call.)
3. Send the form token both as a cookie and in the `&__RequestVerificationToken=` body field.

### 5.3 Request body (form-urlencoded)

| Field | Example | Notes |
| ------- | ------- | ----- |
| `HasMultipleUsageTypes` | `false` | |
| `FileFormat` | `download-usage-csv` | |
| `SelectedFormat` | `2` | |
| `ThirdPartyPODID` | *(empty)* | |
| `SelectedServiceType` | `1` | `1`=Electric, `2`=Water, `4`=Natural Gas, `23`=Billing (from the Dashboard service-type buttons) |
| `Meters[0].Value` | `74352` | **Internal numeric meter id** — see §5.5 |
| `Meters[0].Selected` | `true` | |
| `SelectedInterval` | `6` | `3`=15-min, `4`=30-min, `5`=Hourly, `6`=Daily, `8`=Weekly, `9`=Monthly |
| `SelectedUsageType` | `1` | |
| `Start` / `End` | `2025-07-14` | `YYYY-MM-DD` |
| `ColumnOptions[0..2]` / `RowOptions[0..2]` | ReadDate / UsageDirection / Consumption | Cosmetic; does **not** change the CSV columns |
| `__RequestVerificationToken` | *(form token)* | |

### 5.4 CSV response schema

The returned CSV **always** has this header regardless of the ColumnOptions requested:

```csv
Start,Usage Direction,kWh
"07/14/2025 12:00:00 AM","Delivered","36.28"
"07/15/2025 12:00:00 AM","Delivered","41.34"
```

- `Start` — local timestamp, format `MM/DD/YYYY hh:mm:ss AM/PM`.
- `Usage Direction` — `Delivered` (consumption from grid) or `Received` (e.g. solar export).
- `kWh` — float. The interval of each row is determined by `SelectedInterval` (`6`=one row/day, `5`=one row/hour, `3`=one row/15-min, etc.).

### 5.5 Meter id mapping (critical gotcha)

`Meters[0].Value` must be the **internal numeric meter id**, NOT the display account number shown in the chart series names. The chart markup exposes both:

| Display (series name) | Internal meter id (use this) | Notes |
| ------------------------- | --------------------------- | ----- |
| `4200010055 (Residential Usage Rg1)` | `74352` | Primary electric meter — returns full data |
| `0000006716` | `63306` | Returned empty CSV in testing (likely inactive/secondary) |

The internal id appears in the Dashboard HTML as `id="meterId-74352"` and in the meter toggle checkboxes (`meterIds` with a JSON-ish `value`). If you only have the display number, scrape `/Dashboard/Chart` to map it to the `meterId-NNNNN` element.

### 5.6 Verified samples (saved to `research-capture/`)

| File | Interval | Rows | Size |
| ---- | -------- | ---- | ---- |
| `sample-usage-daily.csv` | Daily, 365 d | 364 | 16.7 KB |
| `sample-usage-15min.csv` | 15-min, 2 d | 171 | 7.6 KB |

Sample (daily):

```csv
Start,Usage Direction,kWh
"07/14/2025 12:00:00 AM","Delivered","36.28"
"07/15/2025 12:00:00 AM","Delivered","41.34"
"07/16/2025 12:00:00 AM","Delivered","25.06"
```

### 5.7 Reusable library

`my-meter-api` (Python, `requests`, MIT) already implements §5.2–§5.4 exactly: `MyMeterApi(baseUrl, rememberMeCookie, sidCookie, cookieRequestVerificationToken).downloadUsage(meterNumber, start, end, interval)`. Because **Home Assistant is Python**, the integration can either depend on this package or vendor the `MyMeterApi` module directly — avoiding a from-scratch reimplementation. (Its `downloadUsage` parses the CSV into `MyMeterUsageValue` objects with `fromDate`, `interval`, `usage_direction`, `consumption`.)

### 5.8 Other confirmed authenticated endpoints

| Method | Endpoint | Returns |
| ------ | -------- | ------- |
| GET | `/Dashboard` | Page HTML; source of the fresh form `__RequestVerificationToken` |
| GET | `/Dashboard/Chart` | JSON envelope; `AjaxResults[0].Value` = chart HTML (incl. service-type buttons, meter toggles) |
| GET | `/Dashboard/ChartData` | JSON envelope; `Data.series[].data` = `[epochMs, kWh]` monthly points; `Data.tooltipOptions` has locale/currency |
| GET | `/Widget/LoadWidgets?Region=Usage` | JSON envelope; `AjaxResults` = Usage widget HTML |
| GET | `/Alerts/Index` | Full authenticated Alerts page (server-rendered) |
| POST | `/Integration/LoadIntegrationData` | Bootstrap data (called multiple times post-login) |

`/Usage/Index` is **not** a real route (404); usage lives in the Dashboard. The standardized MyMeter `POST /Usage/Download` above is the clean path for actual data.

## 6. Recommended Home Assistant Integration Architecture

Standard **config-flow + coordinator** custom component. Two-tier auth design because of reCAPTCHA (see §3):

**Tier 1 — Login oracle (browser only).** The invisible reCAPTCHA cannot be solved by `aiohttp`/`curl`. A one-time (or on-session-expiry) **browser** step performs the login and extracts the `MM_SID` + `__RequestVerificationToken` cookies. This is the only place a browser is needed; it is the account owner's own credentials in their own browser, so it is the legitimate path.

**Tier 2 — Polling (pure HTTP).** Once the session cookies exist, the integration polls with `aiohttp` (or reuses `my-meter-api`):

```
GET  /Dashboard                         → refresh form __RequestVerificationToken
POST /Usage/Download  (form body §5.3) → text/csv usage
GET  /Dashboard/ChartData            → JSON (monthly summary, currency)
GET  /Alerts/Index                   → HTML (alert/outage status)
```

```
custom_components/rfmu/
├── __init__.py          # async_setup / async_setup_entry
├── config_flow.py       # email + password; triggers browser login oracle
├── api.py               # session mgmt + /Usage/Download + JSON endpoints
├── browser_login.py     # optional: drive Firefox DevTools MCP for reCAPTCHA login
├── coordinator.py       # DataUpdateCoordinator (poll every N min)
├── const.py             # URLs, cookie keys, sensor keys, defaults
├── manifest.json        # domain, iot_class, requirements
├── sensor.py            # SensorEntity entities
└── translations/en.json
```

**`api.py` responsibilities:**

1. Store `MM_SID` / `__RequestVerificationToken` (encrypted in HA store via `config_flow`).
2. `async_refresh_token()` — `GET /Dashboard`, parse form token (§5.2).
3. `async_get_usage(meter_id, start, end, interval)` — `POST /Usage/Download`, parse CSV (§5.4). Reuse `my-meter-api.MyMeterApi.downloadUsage` if vendored.
4. `async_get_alerts()` — `GET /Alerts/Index`, parse status.
5. Handle `302` → re-run the browser login oracle (session expired).

**Sensors to expose:**

- Current period usage (kWh) — from daily CSV sum or `ChartData`
- Last bill amount / amount due / due date — from Billing widget/HTML (route still to be captured)
- Cost to date (currency from `tooltipOptions.currency`)
- Outage / alert status — from `/Alerts/Index`
- Interval (hourly/15-min) usage — from `/Usage/Download`

**`manifest.json`:**

```json
{
  "domain": "rfmu",
  "name": "RFMU MyAccount",
  "iot_class": "cloud_polling",
  "config_flow": true,
  "requirements": ["aiohttp"]
}
```

**Test strategy:** record a session (cookies + sample CSV under `research-capture/`) and replay with `aioresponses`/`vcrpy` so CI doesn't need live creds or reCAPTCHA.

## 7. Open Questions / Next Steps

1. **Billing/payment endpoints** — balance, due date, last bill amount. The Billing service type (`SelectedServiceType=23`) and `/View/Pay Bill` nav link exist; the exact data endpoint (likely a `POST /Billing/...` or a widget under `/Widget/LoadWidgets?Region=Billing`) is not yet captured.
2. **Meter-id discovery without hardcoding** — map display account number → internal id by parsing `/Dashboard/Chart` (`meterId-NNNNN`). Should be automated in `api.py`.
3. **Session lifetime** of `MM_SID` (how often the browser login oracle must re-run).
4. **Confirm `/Home/Login` success shape** vs 2FA/secret-question (hidden `TwoFactorRendered` / `SecretQuestionRendered` fields imply those flows may exist).

### How an agent should proceed

- Billing: log in via browser, open View/Pay Bill, capture the XHR/widget request and JSON/HTML shape; document in §5.8.
- Otherwise: scaffold `custom_components/rfmu/` using §5 + §6; vendor or depend on `my-meter-api` for the download logic.

---

## Appendix A — Proven curl probes (templates for `api.py`)

```bash
# 1) Obtain token + session cookie
curl -s -c cookies.txt -A "<UA>" "https://myaccount.rfmu.org/" -o login_page.html
TOKEN=$(grep -oE 'name="__RequestVerificationToken" type="hidden" value="[^"]*"' login_page.html \
        | head -1 | sed -E 's/.*value="([^"]*)".*/\1/')

# 2) Login — NOTE: a g-recaptcha-response token is REQUIRED (reCAPTCHA is server-enforced, see §3).
# Without it the server returns "Please provide a valid login captcha." even with correct creds.
curl -s -b cookies.txt -c cookies.txt -A "<UA>" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "Referer: https://myaccount.rfmu.org/" \
  --data-urlencode "__RequestVerificationToken=$TOKEN" \
  --data-urlencode "LoginEmail=YOU@EXAMPLE.COM" \
  --data-urlencode "LoginPassword=YOURPASS" \
  --data-urlencode "RememberMe=false" \
  --data-urlencode "ExternalLogin=False" \
  --data-urlencode "TwoFactorRendered=False" \
  --data-urlencode "SecretQuestionRendered=False" \
  --data-urlencode "RedirectUrl=" \
  "https://myaccount.rfmu.org/Home/Login"
# -> {"AjaxResults":[],"Data":{...}}   (Data.LoginErrorMessage set on failure)

# 3) Authenticated request (reuse cookies.txt which now holds MM_SID)
curl -s -b cookies.txt -A "<UA>" "https://myaccount.rfmu.org/Dashboard/Index"
```

## Appendix B — Key files fetched for reference

- `https://myaccount.rfmu.org/dist/js/BaseJs.min.js` — core `processAjax` / `universalCallback` helper (32 KB)
- `https://myaccount.rfmu.org/Scripts/Libs/jquery.extensions.js`
- `https://myaccount.rfmu.org/Scripts/plugins.js`
- Login form markup + hidden fields inspected directly in the login page HTML.
