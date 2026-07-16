# Electric Meter Data — Exploration Findings & TODO

**Exploration date**: 2026-07-15  
**Account**: RFMU (meter 74352 → display 4200010055, rate RG1)

---

## ✅ Already Available / Confirmed

| Data Dimension | Source | Intervals Working | Notes |
| --- | --- | --- | --- |
| **Consumption kWh (Delivered)** | `POST /Usage/Download` | 15-min (3), 30-min (4), Hourly (5), Daily (6), Weekly (8), Billing (7) | Monthly (9) returns header only for short range; wide ranges error |
| **Solar Export (Received)** | Same CSV | Same | No Received data for this account (all rows = Delivered) |
| **Energy Markers** | `GET /Dashboard/ViewEnergyMarkers?meterId=74352` | — | Returns 18KB HTML modal with annotated events (outages, alerts, notes) |
| **Monthly Summary + Comparisons** | `GET /Dashboard/ChartData` | — | Current month + Last Year / 2 Years Ago / 3 Years Ago + Energy Marker series; includes currency (USD), locale |
| **Meter Metadata** | `GET /Dashboard/Chart` (parse `meterId-NNNNN` spans + checkbox values) | — | Internal ID, display number, rate code (RG1, RG1-P), service type |

---

## ❌ NOT Available (or Client-Side Only)

| Dimension | Why / Notes |
| --- | --- |
| **Cost ($)** | `SelectedUsageType=3` in Download returns identical kWh rows; chart "Dollar" mode is client-side kWh × rate conversion. No per-interval cost feed. |
| **Demand (kW)** | No `SelectedUsageType` yields demand; residential meter likely has no demand channel. |
| **Billing Balance / Due Date / Last Bill** | No `/Billing` or `/Account` routes (404); billing data likely only in widget HTML, not a clean API. |
| **Property / Account Details** | `/Property`, `/Account`, `/Service` all 404. Meter metadata only via Dashboard chart HTML. |

---

## ⚠️ Constraints / Limits Discovered

1. **Max date span per interval** — Wide ranges (≥ ~1 year) for intervals 7 (Billing), 8 (Weekly), 9 (Monthly) return HTTP 302 → error page. Must chunk queries or respect undocumented max spans.
2. **Monthly (9) granularity** — Returns 0 data rows for ranges < ~2 months; works only for billing-aligned multi-month spans.
3. **No X-Requested-With on Download** — `POST /Usage/Download` rejects requests with `X-Requested-With: XMLHttpRequest`. The library works without it.

---

## 📋 TODO — Capture Remaining Electric Meter Data

### 1. Expand Interval Coverage in Integration

- [x] Add **Hourly (5)** and **30-min (4)** download to coordinator (currently only Daily + 15-min)
- [x] Add **Weekly (8)** and **Billing (7)** intervals with chunked-range logic (respect max span)
- [x] Document per-interval max safe date range (empirically: Daily/15-min/Hourly handle 1+ year; Weekly/Billing/Monthly need chunking)

### 2. Energy Markers

- [x] Parse `/Dashboard/ViewEnergyMarkers` HTML modal → structured events (type, start/end, description)
- [x] Surface as sensors: `energy_markers_count`, `latest_marker` (with attributes)
- [x] Poll daily on coordinator update

### 3. Meter Metadata Enrichment

- [ ] Extract service address, rate schedule details, multiplier from chart HTML or Property widget
- [ ] Add `meter_serial`, `rate_code`, `service_address` attributes to sensor entities

### 4. Derived Cost Estimation

- [ ] Since cost feed doesn't exist: implement optional `rate_cents_per_kwh` config option
- [ ] Compute `month_to_date_cost`, `latest_interval_cost` from kWh × rate
- [ ] If TOU rates detected (from `timeOfUse` in ChartData), support per-period rate schedules

### 5. Solar/Net-Metering (Received) Support

- [x] Ensure `Received` direction rows are parsed and surfaced (separate sensor or attribute)
- [x] Add `net_kwh = Delivered - Received` for net-metering accounts

### 6. ChartData Enhancements

- [ ] Capture `maxUsage` / `minUsage` / `maxUsageDate` / `minUsageDate` from ChartData → sensors
- [ ] Capture comparison series (Last Year, 2 Years Ago) → trend sensors
- [ ] Capture `tooltipOptions.currency` and `locale` for localization

### 7. Robustness / Edge Cases

- [x] Implement range-chunking for intervals 7/8/9 (auto-split >N months into multiple Download calls)
- [ ] Add retry/backoff on 302/400 from Download endpoint
- [ ] Handle "Insufficient meter data" (400) gracefully — return empty, don't fail update
- [ ] Re-auth flow: when `MM_SID` expires, surface reauth config flow (already scaffolded)

### 8. Billing (Stretch)

- [ ] If billing widget exists, scrape `/Widget/LoadWidgets?Region=Billing` or similar
- [ ] Parse balance, due date, last bill amount from widget HTML

---

## Integration Architecture Notes

- **Auth**: Browser login (reCAPTCHA) → user pastes `MM_SID` + `__RequestVerificationToken` cookies → stored encrypted in HA
- **Polling**: `DataUpdateCoordinator` every 15–30 min
- **Download**: Reuse `my-meter-api` logic (GET /Dashboard → form token → POST /Usage/Download **without** X-Requested-With)
- **Sensors proposed**:
  - `month_to_date_kwh`, `latest_interval_kwh`, `last_reading_time`, `active_alerts` (existing)
  - - `hourly_kwh`, `weekly_kwh`, `billing_period_kwh`, `net_kwh` ✅
  - - `energy_markers_count`, `latest_marker` ✅
  - - `max_kwh_today`, `min_kwh_today` ✅
  - - `cost_estimate` (if rate configured) — TODO

---

## Sample Data Captured (under `research-capture/probe/`)

| File | Interval | Rows | Range |
| --- | --- | --- | --- |
| `usage-15min.csv` | 3 | 4,178 | 2026-06-01 → 2026-07-14 |
| `usage-hourly.csv` | 5 | 1,044 | 2026-06-01 → 2026-07-14 |
| `usage-daily.csv` | 6 | 43 | 2026-06-01 → 2026-07-13 |
| `usage-billing.csv` | 7 | 2 | 2026-06-01 → 2026-07-16 |
| `usage-weekly.csv` | 8 | 5 | 2026-06-07 → 2026-07-16 |
| `energy-markers.json` | — | 18KB HTML | modal content |

---

## ✅ Completed in this session

1. **`api.py`** — Added:
   - `async_get_energy_markers()` — fetches and parses `/Dashboard/ViewEnergyMarkers`
   - `async_get_usage_chunked()` — auto-chunks wide ranges for intervals 7/8/9
   - Removed `X-Requested-With` header (was causing 302 rejection on Download)
   - `parse_energy_markers()` function for parsing marker HTML

2. **`coordinator.py`** — Extended `_async_update_data` to fetch:
   - Hourly usage (latest interval)
   - Weekly usage (year-to-date, chunked)
   - Billing period usage (year-to-date, chunked)
   - Energy markers
   - Computed: net kWh, today's max/min hourly, latest marker

3. **`sensor.py`** — Added 8 new sensor entities:
   - `hourly_kwh`, `weekly_kwh`, `billing_kwh`, `net_kwh`
   - `max_kwh_today`, `min_kwh_today`
   - `energy_markers_count`, `latest_marker` (with attributes)

4. **`const.py`** — Added new sensor keys and `INTERVAL_BILLING = 7`

5. **`translations/en.json`** — Added English translations for all new sensors

---

## Next Immediate Step

1. **Add cost estimation** (optional `rate_cents_per_kwh` config option)
2. **ChartData enhancements** (max/min, YoY comparisons, currency/locale)
3. **Meter metadata enrichment** (service address, rate details)
4. **Robustness**: retry/backoff on 302/400, graceful 400 handling
