# MyMeter

A **generic** Home Assistant integration for any utility that runs the
[MyMeter](https://www.wppienergy.org/) customer portal (for example
RFMU / `myaccount.rfmu.org`, and other WPPI Energy utilities).

Because MyMeter's login is protected by **Google reCAPTCHA**, the integration
cannot log in on its own. You perform the login once in a real browser, then
paste the resulting session cookie (`MM_SID`) and anti-forgery token into the
config flow. Meters are **discovered automatically** from the Dashboard, so you
never have to look up the internal `meterId-NNNNN`.

## How it works

- **Polls** your account for electricity usage and exposes it as sensors.
- **Auto-discovers** your meters from the Dashboard and asks you to pick one.
- **Detects session expiry** (a redirect to the login page) and triggers a
  Home Assistant re-authentication prompt, where you re-paste the two cookie
  values.

## Setup

1. Log in to your MyMeter portal in a browser.
2. Open your browser's developer tools and copy two values for that session:
   - `MM_SID` — the session cookie.
   - `__RequestVerificationToken` — the anti-forgery token (page hidden input
     or the cookie).
3. In Home Assistant, add the **MyMeter** integration and provide:
   - **Base URL** — your portal root, e.g. `https://myaccount.rfmu.org`.
   - **Session Cookie** (`MM_SID`).
   - **Verification Token** (`__RequestVerificationToken`).
4. Select the meter to track from the dropdown.

When the session expires, Home Assistant shows a re-authentication prompt — log
in again in the browser and paste the fresh values.

## Sensors

- **Month to Date Usage** — kWh used since the 1st of the current month.
- **Latest Interval Usage** — kWh of the most recent reading.
- **Active Alerts** — `1` when the Alerts page reports an active alert.
- **Last Reading** — timestamp of the most recent reading.

See the [README](https://github.com/littlejth/rfmu) for full details and the
list of not-yet-implemented features.
