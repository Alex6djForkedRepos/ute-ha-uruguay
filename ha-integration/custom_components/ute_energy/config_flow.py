"""ConfigFlow simple: documento + contraseña."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import CONF_DOCUMENT, CONF_PASSWORD, DOMAIN

_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_DOCUMENT): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class UteEnergyConfigFlow(ConfigFlow, domain=DOMAIN):
    """Flow para autenticar usuario."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            from .api import UteAuthError, UteClient

            client = UteClient()
            try:
                await client.bootstrap()
                await client.login(user_input[CONF_DOCUMENT], user_input[CONF_PASSWORD])
            except UteAuthError:
                errors["base"] = "invalid_auth"
            except Exception:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(user_input[CONF_DOCUMENT])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"UTE Uruguay — {user_input[CONF_DOCUMENT]}",
                    data=user_input,
                )
            finally:
                await client._http.aclose()

        return self.async_show_form(
            step_id="user", data_schema=_SCHEMA, errors=errors
        )
