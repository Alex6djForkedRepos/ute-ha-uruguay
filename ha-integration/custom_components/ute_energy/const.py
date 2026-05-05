"""Constantes para la integración UTE Energy."""
from __future__ import annotations

DOMAIN = "ute_energy"
MANUFACTURER = "UTE"
MODEL_ATTR = "amiType"

CONF_DOCUMENT = "document"  # CI / RUT / BPS
CONF_PASSWORD = "password"

DEFAULT_SCAN_INTERVAL_MIN = 30  # consumption changes slowly
PLAN_DEFAULT = "TRIPLERES17"  # plan más común para residenciales
