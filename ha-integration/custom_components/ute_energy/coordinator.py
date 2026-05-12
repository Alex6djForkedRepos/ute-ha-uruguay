"""DataUpdateCoordinator que envuelve UteClient."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_PLAN, DEFAULT_SCAN_INTERVAL_MIN, DOMAIN, PLAN_BY_TARIFF

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
    # buckets devueltos por la API según el plan tarifario:
    # TRT → {"PUNTA","LLANO","VALLE"}; TRD → {"PUNTA","F_PUNTA"}; TRS → {"TRS"}
    consumption_by_tou_kwh: dict[str, float] = field(default_factory=dict)
    is_interrupted: bool = False
    peak_window: str = ""  # ej. "17:00 a 21:00"
    devices: list[_DeviceData] = field(default_factory=list)
    # Calidad de servicio del departamento (varía por servicePoint).
    # Viene como string "99,9 %"; conversión a float en el sensor.
    quality_department: str = ""
    # Status admin del servicio: "0" cuando todo OK; description suele ser null.
    status_code: str = ""
    status_description: str | None = None

    @property
    def plan_code(self) -> str:
        return PLAN_BY_TARIFF.get(self.service.tariff, DEFAULT_PLAN)

    @property
    def total_consumption_kwh(self) -> float:
        return sum(self.consumption_by_tou_kwh.values())


@dataclass
class _BillingPeriod:
    initial_date: str
    final_date: str
    spending_uyu: float
    consumption_kwh: float


@dataclass
class _LastInvoice:
    doc_number: str  # "T 7507283"
    expiration_date: str  # YYYY-MM-DD
    total_amount: float  # UYU
    has_debt: bool


@dataclass
class UteData:
    accounts: dict[str, dict[str, Any]] = field(default_factory=dict)
    services_by_account: dict[str, list[_ServiceData]] = field(default_factory=dict)
    total_debt_by_account: dict[str, float] = field(default_factory=dict)
    unpaid_count_by_account: dict[str, int] = field(default_factory=dict)
    billing_period_by_account: dict[str, _BillingPeriod] = field(default_factory=dict)
    last_invoice_by_account: dict[str, _LastInvoice] = field(default_factory=dict)
    # Métricas nacionales devueltas por la API quality. Las agrupamos por
    # cuenta (no por servicio) porque su valor no depende del servicePoint
    # — UTE las repite igual en cada llamada. Strings tipo "99,5 %".
    renewable_by_account: dict[str, str] = field(default_factory=dict)
    quality_global_by_account: dict[str, str] = field(default_factory=dict)
    # categoryId → label legible (ej. "1" → "Termotanque"). Cache static
    # del catálogo UTE; se refresca cuando vuelve vacío.
    device_category_labels: dict[str, str] = field(default_factory=dict)


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
        from .api import UteClient

        self._client = UteClient()
        await self._client.bootstrap()
        await self._client.login(self._document, self._password)

    async def async_close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _async_update_data(self) -> UteData:
        from .api import UteAuthError

        if self._client is None:
            await self.async_login()

        data = UteData()
        # Cache del scan previo para no perder labels si la llamada falla.
        prev = self.data
        if prev:
            data.device_category_labels = dict(prev.device_category_labels)
        try:
            today = date.today()
            start = today.replace(day=1).isoformat()
            end = today.isoformat()

            # Catálogo de categorías: cargar una vez por sesión. Es estático
            # (no cambia entre cuentas), así que con una llamada alcanza.
            if not data.device_category_labels:
                try:
                    cats = await self._client.device_categories()
                    data.device_category_labels = {
                        str(c.get("categoryId")): str(c.get("description") or "")
                        for c in cats
                    }
                except Exception as e:  # noqa: BLE001
                    _LOGGER.debug("device_categories failed: %s", e)

            for acc in await self._client.accounts():
                data.accounts[acc.account_id] = {
                    "alias": acc.alias,
                    "address": acc.address,
                }
                # /invoices/unpaids es el endpoint canónico — devuelve totalDebt
                # y la lista de facturas. Reemplaza el legacy /invoices/totalDebt.
                try:
                    unpaid = await self._client.unpaid_invoices(acc.account_id)
                except Exception as e:  # noqa: BLE001 — log y fallback
                    _LOGGER.debug("unpaid_invoices failed: %s", e)
                    unpaid = {"totalDebt": 0, "billsUnpaid": []}
                data.total_debt_by_account[acc.account_id] = float(
                    unpaid.get("totalDebt") or 0
                )
                data.unpaid_count_by_account[acc.account_id] = len(
                    unpaid.get("billsUnpaid") or []
                )
                # Última factura emitida (la más reciente del histórico).
                try:
                    invoices = await self._client.invoices_history(
                        acc.account_id, count=1
                    )
                    if invoices:
                        inv = invoices[0]
                        data.last_invoice_by_account[acc.account_id] = _LastInvoice(
                            doc_number=str(inv.get("docNumber") or ""),
                            expiration_date=str(inv.get("expirationDate") or "")[:10],
                            total_amount=float(inv.get("totalAmount") or 0),
                            has_debt=bool(inv.get("hasDebt")),
                        )
                except Exception as e:  # noqa: BLE001
                    _LOGGER.debug("invoices_history failed: %s", e)
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
                        plan=sd.plan_code,
                        date_from=start,
                        date_to=end,
                    )
                    sd.consumption_by_tou_kwh = {
                        t.tou: t.consumption for t in tous
                    }
                    # Horario pico (sólo aplica TRD/TRT — TRS no tiene punta).
                    if svc.tariff in ("TRD", "TRT"):
                        try:
                            peak = await self._client.peak_window(
                                acc.account_id, svc.service_agreement_id
                            )
                            sd.peak_window = (
                                peak.get("selectedPeakStartDescription")
                                or peak.get("meterPeakStartDescription")
                                or ""
                            )
                        except Exception as e:  # noqa: BLE001
                            _LOGGER.debug("peak_window failed: %s", e)
                    status = await self._client.supply_status(
                        acc.account_id, svc.service_agreement_id, svc.service_point_id
                    )
                    sd.is_interrupted = bool(status.get("isInterrupted"))
                    # Calidad de servicio + % renovable.
                    # globalServiceQuality y renewableSources son nacionales:
                    # los guardamos a nivel cuenta (basta con el primer
                    # servicio que responda). departmentServiceQuality varía
                    # por depto → se queda en el _ServiceData.
                    try:
                        quality = await self._client.service_quality(
                            acc.account_id, svc.service_agreement_id
                        )
                        sd.quality_department = str(
                            quality.get("departmentServiceQuality") or ""
                        )
                        if not data.renewable_by_account.get(acc.account_id):
                            data.renewable_by_account[acc.account_id] = str(
                                (quality.get("demand") or {}).get("renewableSources") or ""
                            )
                        if not data.quality_global_by_account.get(acc.account_id):
                            data.quality_global_by_account[acc.account_id] = str(
                                quality.get("globalServiceQuality") or ""
                            )
                    except Exception as e:  # noqa: BLE001
                        _LOGGER.debug("service_quality failed: %s", e)
                    try:
                        status_short = await self._client.service_status_short(
                            acc.account_id, svc.service_agreement_id
                        )
                        sd.status_code = str(status_short.get("code") or "")
                        sd.status_description = status_short.get("description")
                    except Exception as e:  # noqa: BLE001
                        _LOGGER.debug("service_status_short failed: %s", e)
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
            # Refresh token muerto: forzar reauth ConfigFlow.
            await self.async_close()
            raise ConfigEntryAuthFailed(str(e)) from e
        except Exception as e:  # noqa: BLE001 — HA pide UpdateFailed para errores transitorios
            raise UpdateFailed(str(e)) from e
        return data
