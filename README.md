# HomeAssistant-UTE

Integración modernizada de UTE (Administración Nacional de Usinas y Trasmisiones Eléctricas, Uruguay) para Home Assistant + cliente de referencia documentado para reuso en otros proyectos (volt.uy, etc.).

## Por qué

El proyecto upstream [`gustavoqzdaa/ute_energy`](https://github.com/gustavoqzdaa/ute_energy) quedó congelado en junio 2023 y la lib que delegaba (`aronkahrs-us/api-ute`) ya no existe. Esta integración:

1. Actualiza el cliente al estado real de la app UTE 2026 (capturado del OnePlus 12).
2. Documenta el protocolo en `docs/PROTOCOL.md` para que cualquier stack (Python/TS/Go) lo pueda reimplementar.
3. Reescribe la integración HA usando APIs modernas (`DataUpdateCoordinator`, `ConfigEntry.runtime_data`, sensores con `device_class`/`state_class` correctos).

## Estado por fase

| Fase | Artefacto | Estado |
|------|-----------|--------|
| 1 | `references/` — código upstream importado | ✅ |
| 2 | `docs/PROTOCOL.md` v0 (de lectura del upstream) | ✅ |
| 3 | `captures/apk/v1.0.40/` — APKs del device | ✅ |
| 4 | `tooling/` — mitmproxy CA + apk-mitm patched APK | ⏳ |
| 5 | `captures/flows/` — capturas mitm de la app real | ⏳ |
| 6 | `docs/PROTOCOL.md` v1 (validado con captura real) | ⏳ |
| 7 | `ha-integration/` — custom component HACS | ⏳ |
| 8 | `client-ts/` — cliente TS para volt.uy | ⏳ |

## Layout

```
HomeAssistant-UTE/
├── docs/
│   ├── PROTOCOL.md         # spec portable del protocolo UTE
│   └── CAPTURE.md          # cómo reproducir la captura mitm
├── captures/
│   ├── apk/v1.0.40/        # APKs pulled del OnePlus 12
│   └── flows/              # *.mitm flow files (ignored si tienen tokens)
├── references/
│   └── ute_energy_gustavoqzdaa/  # código upstream 2023, baseline
├── ha-integration/
│   └── custom_components/ute_energy/   # integración modernizada
├── client-py/              # core client puro (sin deps HA)
├── client-ts/              # mismo client en TS para volt.uy
└── tooling/                # apk-mitm output, certs locales
```

## Disclaimer

Esta integración no es oficial ni está afiliada con UTE. Usa una API privada de la app móvil; UTE puede cambiarla sin aviso y romper la integración.
