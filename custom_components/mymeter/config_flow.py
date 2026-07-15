"""Adds config flow for the mymeter integration."""

from __future__ import annotations

from typing import Any, Mapping

import voluptuous as vol
from homeassistant import config_entries, data_entry_flow
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import (
    MyMeterApiClient,
    MyMeterApiClientAuthenticationError,
    MyMeterApiClientCommunicationError,
    MyMeterApiClientError,
)
from .const import (
    CONF_BASE_URL,
    CONF_METER_ID,
    CONF_SCAN_INTERVAL,
    CONF_SESSION_COOKIE,
    CONF_TOKEN,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    LOGGER,
    dump_error,
)


class MyMeterFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for MyMeter."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize transient flow state."""
        self._meters: list[dict] = []
        self._base_url: str | None = None
        self._session_cookie: str | None = None
        self._token: str | None = None
        self._reauth_entry: config_entries.ConfigEntry | None = None

    async def _async_test_connection(
        self,
        base_url: str,
        session_cookie: str,
        token: str,
    ) -> list[dict]:
        """Validate the session cookies and return discovered meters."""
        client = MyMeterApiClient(
            base_url=base_url,
            meter_id="",
            session_cookie=session_cookie,
            token=token,
            session=async_create_clientsession(self.hass),
        )
        return await client.async_get_meters()

    async def async_step_user(
        self,
        user_input: dict | None = None,
    ) -> data_entry_flow.FlowResult:
        """Handle a flow initialized by the user."""
        errors: dict[str, str] = {}
        if user_input is not None:
            base_url = user_input[CONF_BASE_URL].strip().rstrip("/")
            session_cookie = user_input[CONF_SESSION_COOKIE].strip()
            token = user_input[CONF_TOKEN].strip()
            try:
                # Validates the session cookies AND discovers meters.
                meters = await self._async_test_connection(
                    base_url, session_cookie, token
                )
            except MyMeterApiClientAuthenticationError as exception:
                LOGGER.warning(exception)
                errors["base"] = "auth"
            except MyMeterApiClientCommunicationError as exception:
                LOGGER.error(exception)
                errors["base"] = "connection"
            except MyMeterApiClientError as exception:
                LOGGER.exception("Unexpected MyMeter API error: %s", exception)
                dump_error("async_step_user:api", exception)
                errors["base"] = "unknown"
            except Exception as exception:  # pylint: disable=broad-except
                LOGGER.exception(
                    "Unexpected error discovering MyMeter meters: %s", exception
                )
                dump_error("async_step_user", exception)
                errors["base"] = "unknown"
            else:
                if not meters:
                    errors["base"] = "no_meters"
                else:
                    self._base_url = user_input[CONF_BASE_URL]
                    self._session_cookie = user_input[CONF_SESSION_COOKIE]
                    self._token = user_input[CONF_TOKEN]
                    self._meters = meters
                    if len(meters) == 1:
                        return await self.async_step_interval(
                            {CONF_METER_ID: meters[0]["id"]}
                        )
                    return await self.async_step_meter()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_BASE_URL): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.URL,
                        ),
                    ),
                    vol.Required(CONF_SESSION_COOKIE): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD,
                        ),
                    ),
                    vol.Required(CONF_TOKEN): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD,
                        ),
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self,
        entry_data: Mapping[str, Any],
    ) -> data_entry_flow.FlowResult:
        """Initiate re-authentication when the MyMeter session expires."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self,
        user_input: dict | None = None,
    ) -> data_entry_flow.FlowResult:
        """Collect fresh session cookies and update the config entry."""
        errors: dict[str, str] = {}
        entry = self._reauth_entry
        if entry is None:
            return self.async_abort(reason="unknown")
        if user_input is not None:
            try:
                await self._async_test_connection(
                    entry.data[CONF_BASE_URL],
                    user_input[CONF_SESSION_COOKIE].strip(),
                    user_input[CONF_TOKEN].strip(),
                )
            except MyMeterApiClientAuthenticationError as exception:
                LOGGER.warning(exception)
                errors["base"] = "auth"
            except MyMeterApiClientCommunicationError as exception:
                LOGGER.error(exception)
                errors["base"] = "connection"
            except MyMeterApiClientError as exception:
                LOGGER.exception(exception)
                dump_error("async_step_reauth_confirm:api", exception)
                errors["base"] = "unknown"
            else:
                self.hass.config_entries.async_update_entry(
                    entry,
                    data={
                        **entry.data,
                        CONF_SESSION_COOKIE: user_input[CONF_SESSION_COOKIE],
                        CONF_TOKEN: user_input[CONF_TOKEN],
                    },
                )
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SESSION_COOKIE): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD,
                        ),
                    ),
                    vol.Required(CONF_TOKEN): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD,
                        ),
                    ),
                }
            ),
            description_placeholders={"base_url": entry.data[CONF_BASE_URL]},
            errors=errors,
        )

    async def async_step_meter(
        self,
        user_input: dict | None = None,
    ) -> data_entry_flow.FlowResult:
        """Let the user pick which discovered meter to track."""
        if user_input is not None:
            return await self.async_step_interval(user_input)

        # SelectSelectorConfig accepts a list of option objects, not a mapping.
        # A mapping was tolerated by older HA releases, but HA 2026 validates
        # the selector schema and otherwise surfaces only "Unknown error" in
        # the config-flow UI.
        options = [
            {
                "value": meter["id"],
                "label": f'{meter.get("label", "")}'
                + (f' ({meter["rate"]})' if meter.get("rate") else ""),
            }
            for meter in self._meters
            if meter.get("id")
        ]
        LOGGER.debug("Presenting %d discovered MyMeter meter(s)", len(options))
        return self.async_show_form(
            step_id="meter",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_METER_ID): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        ),
                    ),
                }
            ),
        )

    async def async_step_interval(
        self,
        user_input: dict | None = None,
    ) -> data_entry_flow.FlowResult:
        """Collect the scan interval and create the entry."""
        if user_input is not None:
            await self.async_set_unique_id(
                f"{self._base_url}#{user_input[CONF_METER_ID]}"
            )
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=self._base_url or "",
                data={
                    CONF_BASE_URL: self._base_url,
                    CONF_SESSION_COOKIE: self._session_cookie,
                    CONF_TOKEN: self._token,
                    CONF_METER_ID: user_input[CONF_METER_ID],
                    CONF_SCAN_INTERVAL: user_input.get(
                        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                    ),
                },
            )

        return self.async_show_form(
            step_id="interval",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=DEFAULT_SCAN_INTERVAL,
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=300,
                            step=300,
                            mode=selector.NumberSelectorMode.BOX,
                            unit_of_measurement="seconds",
                        )
                    ),
                }
            ),
        )

    @staticmethod
    async def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow."""
        return MyMeterOptionsFlowHandler(config_entry)


class MyMeterOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle the options flow for MyMeter."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self,
        user_input: dict | None = None,
    ) -> data_entry_flow.FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=300,
                            step=300,
                            mode=selector.NumberSelectorMode.BOX,
                            unit_of_measurement="seconds",
                        )
                    ),
                }
            ),
        )
