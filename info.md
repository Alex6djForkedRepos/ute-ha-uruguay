# UTE Energy

Integración Home Assistant para [UTE](https://www.ute.com.uy/) (Administración Nacional de Usinas y Trasmisiones Eléctricas, Uruguay).

Lee tu consumo eléctrico, importe del período, deuda y estado del suministro directamente del backend de la app móvil oficial — sin scrapear la web.

**Sensores creados por suministro:**

- Consumo punta / llano / valle / total del mes (kWh)
- Consumo del período de facturación corriente (kWh)
- Importe estimado del período (UYU)
- Deuda total (UYU)
- Cantidad de facturas impagas
- Estado del suministro (OK / INTERRUMPIDO)

Compatible con el [Energy Dashboard](https://www.home-assistant.io/docs/energy/) de Home Assistant.

## Cómo se usa

Después de instalar:
1. Settings → Devices & Services → Add Integration → "UTE Energy".
2. Ingresá tu documento (CI / RUT / BPS) y la contraseña que usás en la app móvil de UTE.
3. Listo. Los sensores aparecen al toque.

## Disclaimer

No es oficial ni está afiliado con UTE. Usa la API privada de su app móvil; UTE puede cambiarla y romper la integración.
