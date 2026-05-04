# UTE Mobile API — Protocol Reference

> **Versión:** v0.5 (lectura upstream 2023 + análisis estático del `libapp.so` v1.0.40, 2026-05-04).
> **Estado:** El upstream-2023 ya **NO refleja el protocolo real**. La app es Flutter (Dart-AOT compilado a `libapp.so`), migró a OAuth 2.0, y cambió el base-path a `/customersapp/`. Las secciones marcadas `[OBSOLETO]` son del upstream-2023 y se mantienen como referencia histórica; las marcadas `[NUEVO]` salen del análisis estático y serán confirmadas con captura mitm.

## ⚠️ Cambios estructurales desde el upstream

| | upstream-2023 (`gustavoqzdaa/ute_energy`) | app real v1.0.40 |
|---|---|---|
| Stack app | Java/Kotlin nativa | **Flutter** (Dart-AOT en `libapp.so`) |
| Base API | `https://rocme.ute.com.uy/api/` | `https://rocme.ute.com.uy/customersapp/` |
| Auth model | email + phone + OTP custom (UTE-only) | **OAuth 2.0 / OIDC federado** contra ID Uruguay (AGESIC) |
| IdP | UTE (custom) | **`auth.iduruguay.gub.uy`** (gob. UY) |
| Token format | bearer opaco | **JWT firmado por id.gub.uy** (RS256) |
| Smart meter ext. | sólo medidores propios | + **Shelly Cloud** (`/customersapp/device/shelly/tokenize/...`) |

## Auth: OIDC contra ID Uruguay (gub.uy)

UTE delegó toda la autenticación a **ID Uruguay**, el SSO nacional uruguayo operado por AGESIC. Esto se confirma con:

- Logo `assets/flutter_assets/assets/images/ext-oidc-logo.png` = escudo oficial **`gub.uy`**.
- Constantes Dart en `libapp.so`: `gubUyClient`, `gubUySecret`, `gubUyAuthEndpoint`, `gubUyTokenEndpoint`.
- App Link de retorno declarado en `AndroidManifest.xml`: `https://clientes.ute.com.uy/mobileapp` (`autoVerify="true"`).
- `assetlinks.json` en `clientes.ute.com.uy/.well-known/` lista 3 SHA-256 fingerprints de la firma original UTE.

### OIDC Discovery (producción, fetched 2026-05-04)

```
GET https://auth.iduruguay.gub.uy/oidc/v1/.well-known/openid-configuration
```

| Endpoint | URL |
|---|---|
| Issuer | `https://auth.iduruguay.gub.uy` |
| Authorization | `https://auth.iduruguay.gub.uy/oidc/v1/authorize` |
| Token | `https://auth.iduruguay.gub.uy/oidc/v1/token` |
| UserInfo | `https://auth.iduruguay.gub.uy/oidc/v1/userinfo` |
| JWKS | `https://auth.iduruguay.gub.uy/oidc/v1/jwks` |
| Logout | `https://auth.iduruguay.gub.uy/oidc/v1/logout` |

- `response_types_supported`: `["code"]` (Authorization Code Flow)
- `id_token_signing_alg`: `RS256`, `HS256`
- `scopes_supported`: `openid`, `personal_info`, `email`, `document`, `profile`
- `acr_values`: `urn:iduruguay:nid:{0..3}` (Niveles de aseguramiento de identidad)
- Auth en `/token`: **HTTP Basic** con `client_id:client_secret` (NO PKCE).
- Token TTL por defecto: 60 minutos. Refresh manual.
- Custom claims útiles para UTE: `numero_documento`, `tipo_documento`, `pais_documento`, `nombre_completo`, `primer_apellido`, `email`, `rid`.

### Flujo de auth de la app UTE (inferido)

```
┌───────────────┐   1. user toca "Ingresar"   ┌──────────────────────┐
│ App UTE       │ ──────────────────────────▶ │ Custom Tab / browser │
└───────────────┘                              └──────────┬───────────┘
                                                          │ 2. GET /oidc/v1/authorize
                                                          ▼
                          ┌────────────────────────────────────────────────────┐
                          │ auth.iduruguay.gub.uy                              │
                          │   /oidc/v1/authorize?                              │
                          │     response_type=code                             │
                          │     client_id=<gubUyClient>            ← desconocido│
                          │     redirect_uri=https://clientes.ute.com.uy/mobileapp│
                          │     scope=openid+personal_info+document+email      │
                          │     state=<random>                                 │
                          │     [acr_values=urn:iduruguay:nid:1|2]             │
                          └────────────────────────────────────────────────────┘
                                                          │ 3. user autentica (CI + clave / SMS / cédula)
                                                          ▼
                          302 → https://clientes.ute.com.uy/mobileapp?code=…&state=…
                                                          │
                          App captura el redirect via App Link autoVerify
                                                          ▼
┌───────────────┐   4. POST /oidc/v1/token            ┌──────────────────────┐
│ App UTE       │ ──────────────────────────────────▶ │ auth.iduruguay.gub.uy│
│  Basic auth:  │                                     │ devuelve JWT (id+    │
│   client_id:  │                                     │   access_token)      │
│   client_secret│ ◀──────────────────────────────────│                      │
└───────────────┘                                     └──────────────────────┘
                                                          │
                    5. GET https://rocme.ute.com.uy/customersapp/...
                       Authorization: Bearer <access_token JWT>
```

### Lo que falta confirmar ([TBD] críticos)

- **`client_id` exacto de UTE** (`gubUyClient`) — está hardcoded en `libapp.so` pero como string concatenada no aparece en `strings`. Se obtiene capturando la URL `/authorize` cuando la app abre el Custom Tab.
- **`client_secret`** (`gubUySecret`) — idem, hardcoded en `libapp.so`. Necesario para `/oidc/v1/token` con HTTP Basic. Implica que la app es "confidential client" según la spec OIDC, aunque mobile RPs deberían ser public clients con PKCE — decisión cuestionable de AGESIC/UTE.
- **scopes solicitados por UTE** (subset de los 5 disponibles).
- **`acr_values`** (nivel de aseguramiento exigido por UTE).
- **Si UTE valida directamente el JWT de id.gub.uy** o si lo intercambia por su propio token contra `/customersapp/...`.

## Bloqueo actual: anti-tamper Dart-side

La app implementa un check de integridad a nivel Dart que loguea `is tampered: true` cuando la firma SHA-256 del APK no coincide con una de las 3 firmas válidas declaradas en `https://clientes.ute.com.uy/.well-known/assetlinks.json`. Apenas `is tampered=true`, la app cierra la `MainActivity` antes de hacer cualquier request.

Implicación: `apk-mitm` (que inyecta un `network_security_config` permisivo y resigna con cert debug) **no es suficiente** para esta app. Hay tres caminos para desbloquear:

1. **Frida-gadget + objection patchapk**: re-empacar el APK con Frida-gadget y un script que hookee la función Dart que devuelve `is tampered`. Requiere localizar el offset en el `libapp.so` AOT — más laborioso pero estándar.
2. **Capturar sólo la URL de `/authorize`** desde la app oficial sin patchar, leyendo `adb logcat` del tag de Chrome/Custom Tab. Eso da `client_id` + `redirect_uri` + scopes pero NO el `client_secret`.
3. **Saltar la app móvil**: implementar la integración HA usando el flujo web de `https://clientes.ute.com.uy` (login interactivo en browser, persistir cookies/session, scrape del backend). Requiere captura de la SPA web que es trivial (sin pinning).

## Sección histórica — upstream 2023 [OBSOLETO]


Esta es una API privada usada por la app móvil de UTE. No está documentada públicamente. El propósito de este documento es habilitar reimplementaciones en cualquier stack (Python para Home Assistant, TS para volt.uy, Go, etc.).

## 1. Transport

| Campo | Valor |
|-------|-------|
| Base URL | `https://rocme.ute.com.uy/api/` |
| Protocolo | HTTPS (TLS) |
| Encoding | JSON, `application/json; charset=utf-8` |
| Compresión | gzip aceptada |
| Auth | Bearer token (ver §2) |

## 2. Headers

Headers que el upstream envía en cada request:

```
X-Client-Type: Android
Content-Type: application/json; charset=utf-8
Host: rocme.ute.com.uy
User-Agent: okhttp/3.8.1                               # [TBD] sospechoso, verificar
Accept-Encoding: gzip
Connection: keep-alive
Accept: */*
Authorization: Bearer <service_token>                  # tras login
```

> ⚠️ El upstream además construye un `User-Agent` falsificado tipo *Xiaomi Mi Home* (`Android-7.1.1-1.0.0-ONEPLUS A3010-...-APP/xiaomi.smarthome APPV/62830`) pero **nunca lo manda al servidor** — queda como atributo y no se inyecta en headers. Se asume que UTE no inspecciona UA. **[TBD]** confirmar con captura.

## 3. Autenticación

Flujo de tres pasos: registro → OTP por SMS → token de servicio.

### 3.1 Registrar usuario / pedir OTP

```
POST /api/v1/users/register
{
  "UserId": 0,
  "Name": "<email>",
  "Email": "<email>",
  "PhoneNumber": "598XXXXXXXX",
  "IsValidated": false,
  "IsBanned": false,
  "UniqueId": null
}
```

UTE responde con `{ "result": <int>, "success": bool, ... }` y dispara un SMS al teléfono indicado con un código de validación.

> El número debe tener **11 dígitos** y empezar con `598` (cód. país UY).

### 3.2 Validar OTP

```
POST /api/v1/users/validate
{ "ValidationCode": "<código del SMS>" }
```

Respuesta `{ "success": true|false, ... }`. Sin éxito el flujo se aborta.

### 3.3 Solicitar service token

```
POST /api/v1/token
{ "Email": "<email>", "PhoneNumber": "598XXXXXXXX" }
```

> ⚠️ La respuesta es **texto plano**, no JSON — el body completo es el token. Se usa luego como `Authorization: Bearer <token>`.

**[TBD]** confirmar:
- ¿Tiene expiración? ¿Hay refresh? El upstream re-loguea cada arranque.
- ¿Se puede reusar el mismo `Email+Phone` desde HA y desde la app móvil simultáneamente?

## 4. Cuentas y suministros

### 4.1 Listar cuentas (puntos de suministro)

```
GET /api/v1/accounts
→ { "data": [ { "accountServicePointId": "...", "servicePointAddress": "...", ... } ], "success": true }
```

### 4.2 Detalle de una cuenta + agreement

```
GET /api/v1/accounts/{accountServicePointId}
→ { "data": { "agreementInfo": {
      "serviceAgreementId": "...",
      "tariff": "TRS|TRD|TRT",
      "voltage": "...",
      "contractedPowerOnPeak": ...,
      "contractedPowerOnValley": ...,
      "contractedPowerOnFlat": ...
    } }, "success": true }
```

Tarifas conocidas:
- `TRS` — Tarifa Residencial Simple
- `TRD` — Tarifa Residencial Doble Horario
- `TRT` — Tarifa Residencial Triple Horario

### 4.3 Horario punta (sólo TRT/TRD)

```
GET /api/v1/accounts/{accountServicePointId}/peak
→ { "data": { "selectedPeakStartDescription": "...", "meterPeakStartDescription": "..." } }
```

### 4.4 Feature flag — pico seleccionable

```
POST /api/v1/misc/behaviour
{ "Name": "IsTariffPeakSelectionAvailable", "Value": null, "accountServicePointId": "..." }
→ { "success": true|false }
```

**[TBD]** otros `Name` posibles que la app real pueda chequear (ej. `IsRemoteReadingAvailable`, autoconsumo solar, recargas, etc.).

## 5. Facturación

### 5.1 Histórico de facturas (rango fijo)

```
GET /api/v1/invoices/{accountServicePointId}/1/36
→ { "data": { "invoices": [
      { "month": 1..12, "year": YYYY, "monthCharges": <UYU>, ... }
    ] }, "success": true }
```

> Path `1/36` significa, según el upstream, "página 1, hasta 36 ítems" (≈ 3 años). **[TBD]** validar con captura — podría ser `desde/hasta` en otra unidad.

### 5.2 Chart de consumo

```
GET /api/v2/invoices/chart/{accountServicePointId}
→ { "data": [ { "consumosActiva": { "unaSerie": [
      { "id": int, "categoryLong": <kWh>, "value": <num>, ... }
    ] } } ], "success": true }
```

Devuelve series mensuales de consumo activo. Hay otras series (`consumosReactiva`, picos por horario) que el upstream **no** consume — explorar en la captura real.

## 6. Lectura del medidor (smart meter)

Sólo aplica a cuentas con medidor inteligente. La lectura es asíncrona: se solicita y luego se polea hasta que el medidor responde.

### 6.1 Solicitar lectura

```
POST /api/v1/device/readingRequest
{ "accountServicePointId": "..." }
→ { "success": true|false }
```

### 6.2 Polling de la lectura

```
GET /api/v1/device/{accountServicePointId}/lastReading/30
→ { "result": <status_code>, "data": { "readings": [
      { "tipoLecturaMGMI": "V1"|"I1"|"RELAY_ON"|..., "valor": "<string>" }
    ] } }
```

| `result` | Significado |
|----------|-------------|
| `51` | Lectura en progreso, reintentar |
| otros | Lectura completada (códigos a documentar) |

> El upstream poolea con `time.sleep(3)` hasta que `result != 51`. Sin timeout máximo configurado — **[TBD]** debería tener cap.

Magnitudes conocidas por `tipoLecturaMGMI`:
- `V1` — voltaje (V)
- `I1` — corriente (A)
- `RELAY_ON` — estado del relé del medidor (`true|false` como string)

> Potencia instantánea: `V1 * I1`, calculado client-side.

**[TBD]** mapear el resto de `tipoLecturaMGMI` que la app real pueda exponer (P1, kWh totales, energía reactiva, factor de potencia, etc.).

## 7. Endpoints conocidos (resumen)

| Endpoint | Método | Auth | Descripción |
|---|---|---|---|
| `/api/v1/users/register` | POST | — | Pedir OTP por SMS |
| `/api/v1/users/validate` | POST | — | Validar OTP |
| `/api/v1/token` | POST | — | Obtener service token (texto plano) |
| `/api/v1/accounts` | GET | Bearer | Listar cuentas |
| `/api/v1/accounts/{id}` | GET | Bearer | Detalle + agreement |
| `/api/v1/accounts/{id}/peak` | GET | Bearer | Horario punta |
| `/api/v1/misc/behaviour` | POST | Bearer | Feature flags |
| `/api/v1/invoices/{id}/1/36` | GET | Bearer | Histórico facturación |
| `/api/v2/invoices/chart/{id}` | GET | Bearer | Series de consumo |
| `/api/v1/device/readingRequest` | POST | Bearer | Pedir lectura medidor |
| `/api/v1/device/{id}/lastReading/30` | GET | Bearer | Polling de lectura |

## 8. Errores

- HTTP `401` → token inválido o expirado (`UteApiAccessDenied`).
- HTTP `403` → permiso insuficiente (`UteApiUnauthorized`).
- Otros HTTP no-2xx → `UteEnergyException`.
- HTTP 200 con `success: false` → error de aplicación; campo `errors` (array) puede traer `{ "text": "..." }` con mensaje legible.

## 9. Pendientes a validar/descubrir con la captura real

- [ ] User-Agent real de la app v1.0.40.
- [ ] ¿Pinea certificados? (Determina cómo bypass: apk-mitm vs Frida.)
- [ ] ¿Hay refresh token / tiene TTL el service token?
- [ ] Endpoints adicionales que el upstream nunca capturó:
  - Notificaciones / push registration.
  - Pagos / medios de pago.
  - Recargas (servicio prepago).
  - Reportes de cortes / incidencias (alumbrado público, calidad de servicio).
  - Autoconsumo solar / generación.
  - Mensajería con UTE.
  - Estados de obras, cambios de potencia, modificación de tarifa.
- [ ] Esquema completo de `result` codes en `lastReading`.
- [ ] Esquema completo de `tipoLecturaMGMI`.
- [ ] Otros `Name` válidos en `/misc/behaviour`.
- [ ] Headers requeridos vs opcionales (probable que `X-Client-Type` sea fingerprint).

## Referencias

- `references/ute_energy_gustavoqzdaa/` — código upstream 2023, base de este documento.
- `captures/apk/v1.0.40/` — APKs decompilables de la app móvil actual.
- `captures/flows/` — capturas mitmproxy (cuando estén).
