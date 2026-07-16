"""API client for the generic MyMeter integration."""

from __future__ import annotations

import csv
import datetime
import json
import logging
import re
import socket
from html.parser import HTMLParser
from typing import Any

import aiohttp
import async_timeout

_LOGGER = logging.getLogger(__package__)


class MyMeterApiClientError(Exception):
    """Exception to indicate a general API error."""


class MyMeterApiClientAuthenticationError(MyMeterApiClientError):
    """Exception to indicate an authentication error."""


class MyMeterApiClientCommunicationError(MyMeterApiClientError):
    """Exception to indicate a communication error."""


class _RequestVerificationTokenParser(HTMLParser):
    """Parse the hidden ``__RequestVerificationToken`` input from an HTML page."""

    def __init__(self) -> None:
        """Initialize the parser."""
        super().__init__()
        self.token: str | None = None

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        """Capture the token value from the matching input element."""
        if tag == "input":
            attrs_dict = dict(attrs)
            if (
                attrs_dict.get("name") == "__RequestVerificationToken"
                and "value" in attrs_dict
            ):
                self.token = attrs_dict["value"]

    def get_token(self) -> str | None:
        """Return the parsed token, if found."""
        return self.token


_METER_SPAN_RE = re.compile(r'id="meterId-(\d+)">([^<]+)</span>')
_METER_CB_RE = re.compile(r'name="meterIds"[^>]*value="(\[.*?\])"', re.S)
_RATE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 \-]*$")


def parse_meters(html: str) -> list[dict]:
    """Parse the Dashboard meter-list HTML into meter records.

    Each meter is rendered as a checkbox named ``meterIds`` (its value encodes
    the internal id + rate) followed by a
    ``<span id="meterId-NNNNN">DISPLAY</span>``. Returns a list of
    dicts: ``{"id": <internal numeric>, "label": <display number>,
    "rate": <str|None>}``. The internal ``id`` is what the
    ``/Usage/Download`` endpoint expects as ``Meters[0].Value``.
    """
    # id -> display number (from the spans)
    labels: dict[str, str] = {}
    for match in _METER_SPAN_RE.finditer(html):
        labels.setdefault(match.group(1), match.group(2).strip())

    # id -> rate code (from the checkboxes, matched by the leading id)
    rates: dict[str, str] = {}
    for match in _METER_CB_RE.finditer(html):
        decoded = match.group(1).replace("&quot;", '"')
        # The value is a JSON-ish array that may be double-escaped in the
        # wild, so try json.loads first and fall back to the raw string.
        try:
            arr = json.loads(decoded)
            inner = str(arr[0]) if isinstance(arr, list) and arr else decoded
        except ValueError:
            inner = decoded
        lead = re.search(r"(\d+)", inner)
        if not lead:
            continue
        meter_id = lead.group(1)
        if meter_id in rates:
            continue
        for segment in inner.split('"'):
            if segment and _RATE_RE.match(segment):
                rates[meter_id] = segment
                break

    return [
        {"id": meter_id, "label": label, "rate": rates.get(meter_id)}
        for meter_id, label in labels.items()
    ]


def parse_usage_csv(text: str) -> list[dict]:
    """Parse the MyMeter usage CSV into a list of usage records.

    The CSV always has the header ``Start,Usage Direction,kWh``.
    Returns a list of dicts: ``{"start": datetime, "direction": str, "kwh": float}``.
    """
    usage_values: list[dict] = []
    reader = csv.reader(text.splitlines(), delimiter=",")
    try:
        next(reader)
    except StopIteration:
        return usage_values
    for row in reader:
        if len(row) < 3:
            continue
        try:
            read_date = datetime.datetime.strptime(row[0], "%m/%d/%Y %I:%M:%S %p")
            usage_direction = row[1].strip()
            consumption = float(row[2])
        except (ValueError, IndexError):
            continue
        usage_values.append(
            {
                "start": read_date,
                "direction": usage_direction,
                "kwh": consumption,
            }
        )
    return usage_values


class MyMeterApiClient:
    """Async API client for MyMeter sites."""

    def __init__(
        self,
        base_url: str,
        meter_id: str,
        session_cookie: str,
        token: str,
        session: aiohttp.ClientSession,
    ) -> None:
        """Initialize the client."""
        self._base_url = (base_url or "").strip().rstrip("/")
        self._meter_id = (meter_id or "").strip()
        self._session_cookie = (session_cookie or "").strip()
        # The user-pasted ``__RequestVerificationToken`` *cookie* value.
        # ASP.NET anti-forgery requires this in the ``Cookie`` header; the
        # per-request *form* token (parsed from /Dashboard) is sent in the POST
        # body instead -- they must NOT be the same value.
        self._cookie_token = (token or "").strip()
        self._form_token = ""
        self._session = session

    def _cookie_header(self) -> dict[str, str]:
        """Build the ``Cookie`` header.

        Tolerates the user pasting either a bare ``MM_SID`` value
        (``CfDJ8...``) or the full cookie string (``MM_SID=CfDJ8...``) — we
        never double-prefix.
        """
        raw = (self._session_cookie or "").strip()
        if raw and "MM_SID=" not in raw:
            cookie = f"MM_SID={raw}"
        else:
            cookie = raw
        token = self._cookie_token or ""
        return {"Cookie": f"{cookie}; __RequestVerificationToken={token}"}

    async def async_refresh_token(self) -> str:
        """Fetch a fresh form ``__RequestVerificationToken`` from ``/Dashboard``."""
        text = await self._api_wrapper(
            method="get",
            url=f"{self._base_url}/Dashboard",
            as_text=True,
        )
        parser = _RequestVerificationTokenParser()
        parser.feed(text)
        token = parser.get_token()
        if not token:
            msg = "Failed to parse request verification token from /Dashboard"
            raise MyMeterApiClientAuthenticationError(msg)
        self._form_token = token
        return token

    async def async_get_usage(
        self,
        start: datetime.date,
        end: datetime.date,
        interval: int = 6,
    ) -> list[dict]:
        """Download usage CSV for the given meter/range/interval."""
        # The POST body needs a fresh form anti-forgery token, not the cookie
        # token, so refresh it from /Dashboard immediately before downloading.
        await self.async_refresh_token()
        body = self._build_usage_body(start, end, interval)
        response_text = await self._api_wrapper(
            method="post",
            url=f"{self._base_url}/Usage/Download",
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            as_text=True,
        )
        return parse_usage_csv(response_text)

    async def async_get_dashboard(self) -> dict:
        """Return the ``Data`` dict from ``/Dashboard/ChartData``."""
        return await self._api_wrapper(
            method="get",
            url=f"{self._base_url}/Dashboard/ChartData",
            as_json=True,
        )

    async def async_get_alerts(self) -> str:
        """Return the Alerts page HTML as text."""
        return await self._api_wrapper(
            method="get",
            url=f"{self._base_url}/Alerts/Index",
            as_text=True,
        )

    async def async_get_meters(self) -> list[dict]:
        """Return the meters available to the logged-in account.

        The meter list lives in the chart HTML returned by ``/Dashboard/Chart``
        (a JSON envelope whose ``AjaxResults[].Value`` is the chart markup).
        """
        text = await self._api_wrapper(
            method="get",
            url=f"{self._base_url}/Dashboard/Chart",
            as_text=True,
        )
        try:
            envelope = json.loads(text)
        except (ValueError, TypeError):
            _LOGGER.debug(
                "Dashboard/Chart response was not valid JSON; no meters found"
            )
            return []
        if not isinstance(envelope, dict):
            _LOGGER.debug(
                "Dashboard/Chart envelope was not an object (got %s); "
                "no meters found",
                type(envelope).__name__,
            )
            return []
        meters: list[dict] = []
        seen: set[str] = set()
        for result in envelope.get("AjaxResults", []):
            if not isinstance(result, dict):
                continue
            value = result.get("Value") or ""
            for meter in parse_meters(value):
                meter_id = meter.get("id")
                if meter_id and meter_id not in seen:
                    seen.add(meter_id)
                    meters.append(meter)
        return meters

    async def async_get_energy_markers(self) -> list[dict]:
        """Fetch and parse energy markers for the configured meter."""
        text = await self._api_wrapper(
            method="get",
            url=f"{self._base_url}/Dashboard/ViewEnergyMarkers",
            as_text=True,
        )
        try:
            envelope = json.loads(text)
        except (ValueError, TypeError):
            _LOGGER.debug(
                "ViewEnergyMarkers response was not valid JSON; no markers found"
            )
            return []
        if not isinstance(envelope, dict):
            return []
        markers_html = ""
        for result in envelope.get("AjaxResults", []):
            if isinstance(result, dict) and result.get("Value"):
                markers_html = result["Value"]
                break
        return parse_energy_markers(markers_html)

    async def async_get_usage_chunked(
        self,
        start: datetime.date,
        end: datetime.date,
        interval: int = 6,
        max_span_days: int | None = None,
    ) -> list[dict]:
        """Download usage CSV with automatic range chunking.

        Intervals 7 (Billing), 8 (Weekly), 9 (Monthly) reject wide ranges
        (HTTP 302 → error). This method splits the range into safe chunks
        and concatenates results.
        """
        # Default safe spans per interval (empirically determined)
        safe_spans = {
            3: 365,   # 15-min
            4: 365,   # 30-min
            5: 365,   # Hourly
            6: 365,   # Daily
            7: 90,    # Billing - ~3 billing cycles
            8: 120,   # Weekly - ~4 months
            9: 180,   # Monthly - ~6 months
        }
        span = max_span_days or safe_spans.get(interval, 365)
        
        all_usage: list[dict] = []
        current_start = start
        while current_start < end:
            current_end = min(current_start + datetime.timedelta(days=span), end)
            try:
                chunk = await self.async_get_usage(current_start, current_end, interval)
                all_usage.extend(chunk)
            except MyMeterApiClientAuthenticationError:
                raise
            except MyMeterApiClientError as err:
                _LOGGER.warning(
                    "Usage chunk %s..%s failed: %s",
                    current_start, current_end, err
                )
            current_start = current_end + datetime.timedelta(days=1)
        
        # Deduplicate by (start, direction) in case of overlap
        seen = set()
        deduped = []
        for item in all_usage:
            key = (item["start"], item["direction"])
            if key not in seen:
                seen.add(key)
                deduped.append(item)
        
        # Sort by start time
        deduped.sort(key=lambda x: x["start"])
        return deduped

    def _build_usage_body(
        self,
        start: datetime.date,
        end: datetime.date,
        interval: int,
    ) -> str:
        """Build the form-encoded ``/Usage/Download`` body."""
        values = {
            "HasMultipleUsageTypes": "false",
            "FileFormat": "download-usage-csv",
            "SelectedFormat": "2",
            "ThirdPartyPODID": "",
            "SelectedServiceType": "1",
            "Meters[0].Value": self._meter_id,
            "Meters[0].Selected": "true",
            "SelectedInterval": str(interval),
            "SelectedUsageType": "1",
            "Start": start.strftime("%Y-%m-%d"),
            "End": end.strftime("%Y-%m-%d"),
            "ColumnOptions[0].Value": "ReadDate",
            "ColumnOptions[0].Name": "ReadDate",
            "ColumnOptions[0].Checked": "false",
            "ColumnOptions[1].Value": "UsageDirection",
            "ColumnOptions[1].Name": "UsageDirection",
            "ColumnOptions[1].Checked": "false",
            "ColumnOptions[2].Value": "Consumption",
            "ColumnOptions[2].Name": "Consumption",
            "ColumnOptions[2].Checked": "false",
            "RowOptions[0].Value": "ReadDate",
            "RowOptions[0].Name": "Read%20Date",
            "RowOptions[0].Desc": "false",
            "RowOptions[1].Value": "UsageDirection",
            "RowOptions[1].Name": "Usage%20Direction",
            "RowOptions[1].Desc": "false",
            "RowOptions[2].Value": "Consumption",
            "RowOptions[2].Name": "kWh",
            "RowOptions[2].Desc": "false",
            "__RequestVerificationToken": self._form_token or self._cookie_token,
        }
        return "&".join(f"{key}={value}" for key, value in values.items())

    async def _api_wrapper(
        self,
        method: str,
        url: str,
        data: str | None = None,
        headers: dict | None = None,
        *,
        as_text: bool = False,
        as_json: bool = False,
    ) -> Any:
        """Wrap a request with timeout and error handling."""
        try:
            async with async_timeout.timeout(10):
                response = await self._session.request(
                    method=method,
                    url=url,
                    headers={
                        "Referer": f"{self._base_url}/Dashboard",
                        **self._cookie_header(),
                        **(headers or {}),
                    },
                    data=data,
                    allow_redirects=False,
                )
                if response.status in (401, 403, 302, 301):
                    msg = (
                        f"Authentication failed ({response.status}) for {url}"
                    )
                    raise MyMeterApiClientAuthenticationError(msg)
                response.raise_for_status()
                if as_json:
                    return await response.json()
                text = await response.text()
                # ASP.NET returns an HTTP 200 AJAX "Redirect" envelope (instead of
                # a real 302) when the session/token is rejected; surface as auth.
                if '"Action":"Redirect"' in text:
                    msg = f"Session rejected (AJAX redirect) for {url}"
                    raise MyMeterApiClientAuthenticationError(msg)
                return text
        except MyMeterApiClientAuthenticationError:
            raise
        except TimeoutError as exception:
            msg = f"Timeout error fetching information - {exception}"
            raise MyMeterApiClientCommunicationError(msg) from exception
        except (aiohttp.ClientError, socket.gaierror) as exception:
            msg = f"Error fetching information - {exception}"
            raise MyMeterApiClientCommunicationError(msg) from exception
        except Exception as exception:  # pylint: disable=broad-except
            msg = f"Something really wrong happened! - {exception}"
            raise MyMeterApiClientError(msg) from exception


# --- Energy markers parsing ---

_MARKER_ID_RE = re.compile(r'data-marker-id="([^"]*)"')
_MARKER_TITLE_RE = re.compile(r'class="[^"]*marker-title[^"]*"[^>]*>([^<]*)</span>')
_MARKER_DATE_RE = re.compile(r'class="[^"]*marker-date[^"]*"[^>]*>([^<]*)</span>')
_MARKER_DESC_RE = re.compile(r'class="[^"]*marker-description[^"]*"[^>]*>([^<]*)</span>')
_MARKER_TYPE_RE = re.compile(r'class="[^"]*marker-type[^"]*"[^>]*>([^<]*)</span>')


def parse_energy_markers(html: str) -> list[dict]:
    """Parse the Energy Markers modal HTML into structured events.

    The modal is returned as HTML inside an AjaxResults envelope Value field.
    Returns list of dicts: {id, title, date, description, type}.
    """
    markers: list[dict] = []
    ids = [m.group(1) for m in _MARKER_ID_RE.finditer(html)]
    titles = [m.group(1) for m in _MARKER_TITLE_RE.finditer(html)]
    dates = [m.group(1) for m in _MARKER_DATE_RE.finditer(html)]
    descs = [m.group(1) for m in _MARKER_DESC_RE.finditer(html)]
    types = [m.group(1) for m in _MARKER_TYPE_RE.finditer(html)]
    for i in range(min(len(ids), len(titles), len(dates))):
        markers.append(
            {
                "id": ids[i].strip(),
                "title": titles[i].strip() if i < len(titles) else "",
                "date": dates[i].strip() if i < len(dates) else "",
                "description": descs[i].strip() if i < len(descs) else "",
                "type": types[i].strip() if i < len(types) else "unknown",
            }
        )
    return markers
