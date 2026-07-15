# MyMeter for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![hassfest](https://github.com/littlejth/rfmu/actions/workflows/validate.yaml/badge.svg)](https://github.com/littlejth/rfmu/actions/workflows/validate.yaml)
[![Minimum HA Version](https://img.shields.io/badge/HA-%E2%89%A5%202024.12.0-41BDF5.svg)](https://www.home-assistant.io)

A **generic** Home Assistant integration for any utility that runs the
[MyMeter](https://www.wppienergy.org/) customer portal (for example
RFMU / `myaccount.rfmu.org`, and other WPPI Energy utilities).

It polls your account for electricity usage and exposes it as sensors — no
manual scraping required, because the data endpoint returns clean CSV.

## Login & reCAPTCHA

MyMeter's login is protected by Google **reCAPTCHA**, which cannot be solved
from Home Assistant. You therefore perform the login **once in a browser** and
then hand the resulting session cookies to this integration:

1. Log in to your MyMeter portal in a browser.
2. Copy two values from your browser's cookies / page for that session:
   - `MM_SID` — the session cookie.
   - `__RequestVerificationToken` — the anti-forgery token (from the page's
     hidden input or the cookie).
3. In Home Assistant, add the **MyMeter** integration and fill in:
   - **Base URL** — your portal root, e.g. `https://myaccount.rfmu.org`.
   - **Session Cookie** (`MM_SID`).
   - **Verification Token** (`__RequestVerificationToken`).

The config flow validates the cookies immediately by fetching the Dashboard,
and **discovers your meters automatically** — you then pick the meter to track
from a dropdown (no need to find the internal `meterId-NNNNN`).

### When the session expires

Because the `MM_SID` session eventually expires, the integration will detect
the expiry (a redirect to the login page) and Home Assistant will show a
**re-authentication** prompt. Log in to the portal in a browser again, copy the
fresh `MM_SID` cookie and `__RequestVerificationToken`, and paste them into the
prompt — the base URL and meter are kept, so you only re-supply the two
session values.
Because the `MM_SID` session eventually expires, re-run the browser login and
update the credentials when the integration reports an auth error.

## Sensors

- **Month to Date Usage** (`month_to_date_kwh`) — kWh used since the 1st of
  the current month.
- **Latest Interval Usage** (`latest_interval_kwh`) — kWh of the most recent
  reading.
- **Active Alerts** (`active_alerts`) — `1` when the Alerts page reports an
  active alert, else `0`.
- **Last Reading** (`last_reading_time`) — timestamp of the most recent
  reading.

## Not yet implemented

- **Billing balance / amount due / due date** sensors — the billing endpoint
  has not been captured yet (see `RESEARCH.md`). This is tracked as a TODO.

## Credits

The data-download approach is based on the `my-meter-api` library
(<https://github.com/jthoward64/my-meter-api>, MIT).
