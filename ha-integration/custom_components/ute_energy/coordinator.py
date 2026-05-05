"""DataUpdateCoordinator que envuelve UteClient."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_SCAN_INTERVAL_MIN, DOMAIN, PLAN_DEFAULT

_LOGGER = logging.getLogger(__name__)


@dataclass
class _DeviceData:
    """Shelly UTE asociado al suministro."""

    device_id: int
    name: str
    provider: str  # SHELLY
    online: bool  # status == "online"
    category_id: str
    instant_consumption_w: float = 0.0
    voltage_v: float = 0.0
    rssi_dbm: int = 0
    is_device_on: bool = False
    is_in_bypass: bool = False
    is_schedule_active: bool = False
    percentage_of_total_consumption: str = ""


@dataclass
class _ServiceData:
    service: Any  # ute_client.Service
    consumption_punta_kwh: float = 0.0
    consumption_llano_kwh: float = 0.0
    consumption_valle_kwh: float = 0.0
    is_interrupted: bool = False
    devices: list[_DeviceData] = field(default_factory=list)


@dataclass
class _BillingPeriod:
    initial_date: str
    final_date: str
    spending_uyu: float
    consumption_kwh: float


@dataclass
class UteData:
    accounts: dict[str, dict[str, Any]] = field(default_factory=dict)
    services_by_account: dict[str, list[_ServiceData]] = field(default_factory=dict)
    total_debt_by_account: dict[str, float] = field(default_factory=dict)
    billing_period_by_account: dict[str, _BillingPeriod] = field(default_factory=dict)


class UteCoordinator(DataUpdateCoordinator[UteData]):
    """Coordinator: llama al cliente UTE en intervalos y expone datos a sensores."""

    def __init__(self, hass: HomeAssistant, document: str, password: str) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=DEFAULT_SCAN_INTERVAL_MIN),
        )
        self._document = document
        self._password = password
        self._client = None

    async def async_login(self) -> None:
        # Importación tardía para que `requirements` se haya instalado.
        from ute_client import UteClient

        self._client = UteClient()
        await self._client.bootstrap()
        await self._client.login(self._document, self._password)

    async def async_close(self) -> None:
        if self._client:
            await self._client._http.aclose()
            self._client = None

    async def _async_update_data(self) -> UteData:
        from ute_client import UteAuthError

        if self._client is None:
            await self.async_login()

        data = UteData()
        try:
            today = date.today()
            start = today.replace(day=1).isoformat()
            end = today.isoformat()

            for acc in await self._client.accounts():
                data.accounts[acc.account_id] = {
                    "alias": acc.alias,
                    "address": acc.address,
                }
                data.total_debt_by_account[acc.account_id] = (
                    await self._client.total_debt(acc.account_id)
                )
                summary = await self._client.billing_period_summary(acc.account_id)
                data.billing_period_by_account[acc.account_id] = _BillingPeriod(
                    initial_date=summary.initial_date,
                    final_date=summary.final_date,
                    spending_uyu=summary.current_spending_uyu,
                    consumption_kwh=summary.current_consumption_kwh,
                )
                services: list[_ServiceData] = []
                for svc in await self._client.services(acc.account_id):
                    sd = _ServiceData(service=svc)
                    tous = await self._client.consumption_by_tou(
                        svc.service_point_id,
                        plan=PLAN_DEFAULT,
                        date_from=start,
                        date_to=end,
                    )
                    for t in tous:
                        if t.tou == "PUNTA":
                            sd.consumption_punta_kwh = t.consumption
                        elif t.tou == "LLANO":
                            sd.consumption_llano_kwh = t.consumption
                        elif t.tou == "VALLE":
                            sd.consumption_valle_kwh = t.consumption
                    status = await self._client.supply_status(
                        acc.account_id, svc.service_agreement_id, svc.service_point_id
                    )
                    sd.is_interrupted = bool(status.get("isInterrupted"))
                    # Listar Shellys del servicePoint y obtener status en vivo
                    try:
                        dev_resp = await self._client.devices(svc.service_point_id)
                        for dev in dev_resp.get("devices") or []:
                            dd = _DeviceData(
                                device_id=dev.device_id,
                                name=dev.name,
                                provider=dev.provider,
                                online=dev.status == "online",
                                category_id=dev.category_id,
                            )
                            try:
                                ds = await self._client.device_status(dev.device_id)
                                dd.instant_consumption_w = ds.instant_consumption_w
                                dd.voltage_v = ds.voltage_v
                                dd.rssi_dbm = ds.rssi_dbm
                                dd.is_device_on = ds.is_device_on
                                dd.is_in_bypass = ds.is_in_bypass
                                dd.is_schedule_active = ds.is_schedule_active
                                dd.percentage_of_total_consumption = (
                                    ds.percentage_of_total_consumption
                                )
                            except Exception as e:  # pragma: no cover
                                _LOGGER.debug("device_status failed: %s", e)
                            sd.devices.append(dd)
                    except Exception as e:  # pragma: no cover
                        _LOGGER.debug("devices list failed: %s", e)
                    services.append(sd)
                data.services_by_account[acc.account_id] = services
        except UteAuthError as e:
            raise UpdateFailed(f"auth: {e}") from e
        except Exception as e:  # pragma: no cover
            raise UpdateFailed(str(e)) from e
        return data
