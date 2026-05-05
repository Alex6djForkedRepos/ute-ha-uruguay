"""ConfigFlow: documento + contraseña."""
from __future__ import annotations

import hashlib
import logging
from typing import Any

import httpx
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import CONF_DOCUMENT, CONF_PASSWORD, DOMAIN

_LOGGER = logging.getLogger(__name__)

_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_DOCUMENT): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


def _mask_doc(doc: str) -> str:
    """Mostrar 47****63 en lugar de la cédula completa."""
    s = (doc or "").strip()
    if len(s) <= 4:
        return "****"
    return f"{s[:2]}{'*' * (len(s) - 4)}{s[-2:]}"


class UteUruguayConfigFlow(ConfigFlow, domain=DOMAIN):
    """Flow para autenticar usuario."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            from .api import UteApiError, UteAuthError, UteClient

            doc = user_input[CONF_DOCUMENT].strip()
            client = UteClient()
            try:
                await client.bootstrap()
                await client.login(doc, user_input[CONF_PASSWORD])
            except UteAuthError:
                errors["base"] = "invalid_auth"
            except (UteApiError, httpx.HTTPError) as e:
                _LOGGER.warning("UTE bootstrap/login network error: %s", e)
                errors["base"] = "cannot_connect"
            else:
                # unique_id es el hash del documento — no leak de la cédula
                # en logs/storage de HA. Un único entry por documento.
                uid = hashlib.sha256(doc.encode("utf-8")).hexdigest()[:16]
                await self.async_set_unique_id(uid)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"UTE Uruguay ({_mask_doc(doc)})",
                    data={CONF_DOCUMENT: doc, CONF_PASSWORD: user_input[CONF_PASSWORD]},
                )
            finally:
                await client.aclose()

        return self.async_show_form(
            step_id="user", data_schema=_SCHEMA, errors=errors
        )
