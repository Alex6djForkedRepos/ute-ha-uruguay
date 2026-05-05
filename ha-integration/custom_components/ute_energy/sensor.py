"""Sensores expuestos por la integración UTE Energy."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import UteCoordinator, _DeviceData, _ServiceData


@dataclass(frozen=True, kw_only=True)
class _UteSensorDesc(SensorEntityDescription):
    value_fn: Callable[[_ServiceData], Any] = lambda s: None


_SENSORS: tuple[_UteSensorDesc, ...] = (
    _UteSensorDesc(
        key="consumption_punta",
        translation_key="consumption_punta",
        name="Consumo punta (mes)",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=lambda s: s.consumption_punta_kwh,
    ),
    _UteSensorDesc(
        key="consumption_llano",
        translation_key="consumption_llano",
        name="Consumo llano (mes)",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=lambda s: s.consumption_llano_kwh,
    ),
    _UteSensorDesc(
        key="consumption_valle",
        translation_key="consumption_valle",
        name="Consumo valle (mes)",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=lambda s: s.consumption_valle_kwh,
    ),
    _UteSensorDesc(
        key="consumption_total",
        translation_key="consumption_total",
        name="Consumo total (mes)",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=lambda s: (
            s.consumption_punta_kwh + s.consumption_llano_kwh + s.consumption_valle_kwh
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: UteCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = []
    for account_id, services in coordinator.data.services_by_account.items():
        for sd in services:
            for desc in _SENSORS:
                entities.append(_UteSensor(coordinator, account_id, sd, desc))
            entities.append(_StatusSensor(coordinator, account_id, sd))
        entities.append(_DebtSensor(coordinator, account_id))
        entities.append(_BillingSpendingSensor(coordinator, account_id))
        entities.append(_BillingConsumptionSensor(coordinator, account_id))
        entities.append(_UnpaidCountSensor(coordinator, account_id))
        # Shelly UTE devices: un sensor por device por métrica
        for sd in services:
            for dev in sd.devices:
                for desc in _DEVICE_SENSORS:
                    entities.append(
                        _DeviceSensor(coordinator, account_id, sd, dev, desc)
                    )
    async_add_entities(entities)


@dataclass(frozen=True, kw_only=True)
class _DeviceSensorDesc(SensorEntityDescription):
    value_fn: Callable[[_DeviceData], Any] = lambda d: None


_DEVICE_SENSORS: tuple[_DeviceSensorDesc, ...] = (
    _DeviceSensorDesc(
        key="device_power",
        translation_key="device_power",
        name="Potencia instantánea",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        value_fn=lambda d: d.instant_consumption_w,
    ),
    _DeviceSensorDesc(
        key="device_voltage",
        translation_key="device_voltage",
        name="Voltaje",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        value_fn=lambda d: d.voltage_v,
    ),
    _DeviceSensorDesc(
        key="device_rssi",
        translation_key="device_rssi",
        name="RSSI",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        value_fn=lambda d: d.rssi_dbm,
        entity_registry_enabled_default=False,
    ),
    _DeviceSensorDesc(
        key="device_state",
        translation_key="device_state",
        name="Estado",
        value_fn=lambda d: "encendido" if d.is_device_on else "apagado",
    ),
    _DeviceSensorDesc(
        key="device_consumption_share",
        translation_key="device_consumption_share",
        name="Porcentaje del consumo total",
        icon="mdi:chart-pie",
        value_fn=lambda d: d.percentage_of_total_consumption.rstrip("%") or None,
        native_unit_of_measurement="%",
    ),
)


class _DeviceSensor(CoordinatorEntity[UteCoordinator], SensorEntity):
    """Sensor para un Shelly UTE individual (Calefón, A/C, etc)."""

    _attr_has_entity_name = True
    entity_description: _DeviceSensorDesc

    def __init__(
        self,
        coordinator: UteCoordinator,
        account_id: str,
        sd: _ServiceData,
        dev: _DeviceData,
        desc: _DeviceSensorDesc,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = desc
        self._account_id = account_id
        self._service_point_id = sd.service.service_point_id
        self._device_id = dev.device_id
        self._attr_unique_id = f"{account_id}_{dev.device_id}_{desc.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"shelly:{dev.device_id}")},
            name=dev.name,
            manufacturer="Shelly (vía UTE)",
            model=f"Categoría {dev.category_id}",
            via_device=(DOMAIN, f"{account_id}:{sd.service.service_point_id}"),
            configuration_url="https://rocme.ute.com.uy/customersapp",
        )

    def _current_dev(self) -> _DeviceData | None:
        for sd in self.coordinator.data.services_by_account.get(self._account_id, []):
            if sd.service.service_point_id != self._service_point_id:
                continue
            for d in sd.devices:
                if d.device_id == self._device_id:
                    return d
        return None

    @property
    def available(self) -> bool:
        d = self._current_dev()
        return super().available and d is not None and d.online

    @property
    def native_value(self) -> Any:
        d = self._current_dev()
        return self.entity_description.value_fn(d) if d else None


class _UteSensor(CoordinatorEntity[UteCoordinator], SensorEntity):
    """Sensor de consumo TOU."""

    _attr_has_entity_name = True
    entity_description: _UteSensorDesc

    def __init__(
        self,
        coordinator: UteCoordinator,
        account_id: str,
        sd: _ServiceData,
        desc: _UteSensorDesc,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = desc
        self._account_id = account_id
        self._service_point_id = sd.service.service_point_id
        self._attr_unique_id = f"{account_id}_{sd.service.service_point_id}_{desc.key}"
        self._attr_device_info = _device_info(account_id, sd)

    def _current_sd(self) -> _ServiceData | None:
        for sd in self.coordinator.data.services_by_account.get(self._account_id, []):
            if sd.service.service_point_id == self._service_point_id:
                return sd
        return None

    @property
    def native_value(self) -> Any:
        sd = self._current_sd()
        return self.entity_description.value_fn(sd) if sd else None


class _DebtSensor(CoordinatorEntity[UteCoordinator], SensorEntity):
    """Deuda total por cuenta (UYU)."""

    _attr_has_entity_name = True
    _attr_translation_key = "total_debt"
    _attr_name = "Deuda total"
    _attr_native_unit_of_measurement = "UYU"
    _attr_state_class = SensorStateClass.TOTAL

    def __init__(self, coordinator: UteCoordinator, account_id: str) -> None:
        super().__init__(coordinator)
        self._account_id = account_id
        self._attr_unique_id = f"{account_id}_total_debt"
        sd_first = next(
            iter(coordinator.data.services_by_account.get(account_id, [])), None
        )
        self._attr_device_info = (
            _device_info(account_id, sd_first) if sd_first else None
        )

    @property
    def native_value(self) -> Any:
        return self.coordinator.data.total_debt_by_account.get(self._account_id)


class _StatusSensor(CoordinatorEntity[UteCoordinator], SensorEntity):
    """Estado del suministro (OK/INTERRUMPIDO)."""

    _attr_has_entity_name = True
    _attr_translation_key = "supply_status"
    _attr_name = "Estado del suministro"

    def __init__(
        self, coordinator: UteCoordinator, account_id: str, sd: _ServiceData
    ) -> None:
        super().__init__(coordinator)
        self._account_id = account_id
        self._service_point_id = sd.service.service_point_id
        self._attr_unique_id = f"{account_id}_{sd.service.service_point_id}_status"
        self._attr_device_info = _device_info(account_id, sd)

    @property
    def native_value(self) -> Any:
        for sd in self.coordinator.data.services_by_account.get(self._account_id, []):
            if sd.service.service_point_id == self._service_point_id:
                return "INTERRUMPIDO" if sd.is_interrupted else "OK"
        return None


class _BillingSpendingSensor(CoordinatorEntity[UteCoordinator], SensorEntity):
    """Importe estimado del período de facturación corriente (UYU)."""

    _attr_has_entity_name = True
    _attr_translation_key = "billing_spending"
    _attr_name = "Importe estimado del período"
    _attr_native_unit_of_measurement = "UYU"
    _attr_state_class = SensorStateClass.TOTAL

    def __init__(self, coordinator: UteCoordinator, account_id: str) -> None:
        super().__init__(coordinator)
        self._account_id = account_id
        self._attr_unique_id = f"{account_id}_billing_spending"
        sd_first = next(
            iter(coordinator.data.services_by_account.get(account_id, [])), None
        )
        self._attr_device_info = (
            _device_info(account_id, sd_first) if sd_first else None
        )

    @property
    def native_value(self) -> Any:
        bp = self.coordinator.data.billing_period_by_account.get(self._account_id)
        return round(bp.spending_uyu, 2) if bp else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        bp = self.coordinator.data.billing_period_by_account.get(self._account_id)
        if not bp:
            return {}
        return {"period_start": bp.initial_date, "period_end": bp.final_date}


class _BillingConsumptionSensor(CoordinatorEntity[UteCoordinator], SensorEntity):
    """Consumo del período de facturación corriente (kWh)."""

    _attr_has_entity_name = True
    _attr_translation_key = "billing_consumption"
    _attr_name = "Consumo del período"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(self, coordinator: UteCoordinator, account_id: str) -> None:
        super().__init__(coordinator)
        self._account_id = account_id
        self._attr_unique_id = f"{account_id}_billing_consumption"
        sd_first = next(
            iter(coordinator.data.services_by_account.get(account_id, [])), None
        )
        self._attr_device_info = (
            _device_info(account_id, sd_first) if sd_first else None
        )

    @property
    def native_value(self) -> Any:
        bp = self.coordinator.data.billing_period_by_account.get(self._account_id)
        return round(bp.consumption_kwh, 2) if bp else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        bp = self.coordinator.data.billing_period_by_account.get(self._account_id)
        if not bp:
            return {}
        return {"period_start": bp.initial_date, "period_end": bp.final_date}


class _UnpaidCountSensor(CoordinatorEntity[UteCoordinator], SensorEntity):
    """Cantidad de facturas impagas."""

    _attr_has_entity_name = True
    _attr_translation_key = "unpaid_invoices"
    _attr_name = "Facturas impagas"
    _attr_icon = "mdi:file-document-alert"

    def __init__(self, coordinator: UteCoordinator, account_id: str) -> None:
        super().__init__(coordinator)
        self._account_id = account_id
        self._attr_unique_id = f"{account_id}_unpaid_count"
        sd_first = next(
            iter(coordinator.data.services_by_account.get(account_id, [])), None
        )
        self._attr_device_info = (
            _device_info(account_id, sd_first) if sd_first else None
        )

    @property
    def native_value(self) -> Any:
        return self.coordinator.data.unpaid_count_by_account.get(self._account_id, 0)


def _device_info(account_id: str, sd: _ServiceData) -> DeviceInfo:
    s = sd.service
    return DeviceInfo(
        identifiers={(DOMAIN, f"{account_id}:{s.service_point_id}")},
        name=f"{s.short_address}",
        manufacturer=MANUFACTURER,
        model=s.tariff_description,
        sw_version=s.ami_type,
        hw_version=s.meter_id,
        configuration_url="https://rocme.ute.com.uy/customersapp",
    )
