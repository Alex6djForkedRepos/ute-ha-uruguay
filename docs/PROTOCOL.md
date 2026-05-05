# UTE Mobile API — Protocol Reference

> **Versión:** v1.0 (captura mitm real desde AVD x86_64+ARM64 translation, 2026-05-04 21:14).
> **Estado:** Validado contra captura real de `uy.com.ute.customers` v1.0.40. App Flutter Dart-AOT, base API `/customersapp/`, auth federada via IdentityServer propio de UTE → id.gub.uy. **No hace falta hardcodear secrets**: la app se autoconfigura via `POST /customers/setup` que devuelve client_ids/secrets/endpoints en runtime.

## 🔑 Bootstrap zero-secret: el endpoint que cambia todo

Apenas la app arranca y antes del login, hace 4 requests obligatorios. El crítico es el #3:

```
1. GET  /customersapp/flags/SecurityChecksBypass
   → {"active": false}                              # feature flag (server-side disable de checks)

2. POST /customersapp/integrity-check
   {"OS":0,"payload":"<SHA-256 de la firma del APK>"}
   → 200 (vacío)                                    # server valida vs whitelist; si tampered=true responde error

3. POST /customersapp/customers/setup
   {"registrationId":"","deviceInfo":[]}
   → {"uniqueId":"...uuid...",
      "oAuthConfiguration":{
        "authority": "https://identityserver.ute.com.uy",
        "defaultSite": "https://clientes.ute.com.uy",
        "client":  "customers_mobile_app",
        "secret":  "<UUID>",                        # ⚠️ secret rotado por server
        "scope":   "customers.accounts",
        "gubUyClient":  "<id-numérico-en-id.gub.uy>",
        "gubUySecret":  "<secret-rotado>",
        "gubUyAuthEndpoint":  "https://auth.iduruguay.gub.uy/oidc/v1/authorize",
        "gubUyTokenEndpoint": "https://auth.iduruguay.gub.uy/oidc/v1/token"
      }}

4. POST /customersapp/customers/event
   {"uniqueId":"<del-setup>", "eventName":"sec_check_emulator_failed", "eventData":null}
   → 200                                            # telemetría de checks anti-tamper
```

**Implicación para el plugin HA**: no hardcodeamos secrets en el repo. Cada vez que el plugin arranca:
1. Hace `POST /customers/setup` con `{"registrationId":"","deviceInfo":[]}`.
2. Lee `oAuthConfiguration` y guarda en cache.
3. Inicia el flujo OAuth con esos valores.

Si UTE/AGESIC rotan client_secret, el plugin lo recoge automáticamente en el próximo bootstrap. Sin riesgo de que el plugin se rompa por revocación.

## Headers reales (capturados)

```
user-agent: Dart/3.7 (dart:io)             # Flutter HttpClient default — NO X-Client-Type ni nada custom
content-type: application/json; charset=utf-8
accept-encoding: gzip
host: rocme.ute.com.uy
```

El upstream-2023 mandaba `X-Client-Type: Android` y otros headers fingerprint — **la app real 2026 no los manda**. Solo Dart/3.7 default. Eso facilita la implementación: cualquier HTTP client respeta los defaults.

Cookies: el server setea una `<hash>=<value>; HttpOnly; Secure; SameSite=None` por response (sticky session via cookie). Hay que mantenerla en una `Session` persistente en el cliente.

## Server stack identificado

`server: Kestrel` ⇒ ASP.NET Core. Concuerda con `/connect/token` patrón IdentityServer4 (Duende post-2022).

## Flujo OAuth efectivo (broker UTE → id.gub.uy)

UTE NO va directo a id.gub.uy. Tiene un broker IdentityServer propio (`identityserver.ute.com.uy`) que delega a id.gub.uy. La app móvil habla con UTE; UTE coordina con AGESIC.

```
┌─────────┐  /authorize  ┌─────────────────────────┐  /authorize  ┌──────────────────────┐
│ App UTE │ ───────────▶ │ identityserver.ute.com.uy│ ───────────▶ │ auth.iduruguay.gub.uy│
│         │              │  (IdentityServer/Duende)│              │  (AGESIC, OIDC)       │
│         │ ◀─────────── │  client=customers_mobile│ ◀─────────── │  client=292015        │
│         │   token UTE  │                         │   token gub  │                       │
└─────────┘              └─────────────────────────┘              └──────────────────────┘
   ↓ Bearer <UTE-token>
   GET /customersapp/...
```

Token que UTE expone al cliente final es el que UTE emite (no el de gub.uy). El cliente solo necesita autenticarse contra `identityserver.ute.com.uy/connect/token` con `client=customers_mobile_app`+`secret`+`scope=customers.accounts`. **El delegado a gub.uy lo maneja UTE internamente** durante el flujo `/authorize`.

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

## Anti-tamper y su bypass natural

La app implementa un check de integridad a nivel Dart que loguea `is tampered: true` cuando la firma SHA-256 del APK no coincide con una de las 3 firmas válidas declaradas en `https://clientes.ute.com.uy/.well-known/assetlinks.json`. Apenas `is tampered=true`, la app cierra la `MainActivity`.

PERO — el binario tiene un escape hatch del propio UTE:

```
GET https://rocme.ute.com.uy/customersapp/flags/SecurityChecksBypass
→ si el response es truthy, NO se ejecuta el integrity check
```

Strings en `libapp.so` que confirman la cadena:
- `"flags/SecurityChecksBypass"` — el path consultado.
- `"Error checking SecurityChecksBypass flag: "` — log del fail-open / fail-close.
- `"Failed to perform integrity check. "` — el check propio.
- `"is emulator: "`, `"is compromised: "`, `"is tampered: "` — los tres bools que se loguean.

Es un feature flag de servidor pensado para que UTE/devs puedan deshabilitar checks en QA/staging sin recompilar. **Lo aprovechamos**: con un addon de `mitmproxy` que intercepte ese path y responda truthy, la app patcheada arranca normalmente:

```python
# tooling/security_bypass_addon.py
def request(flow):
    if "/flags/SecurityChecksBypass" in flow.request.path:
        flow.response = http.Response.make(200, b'{"value":true,"data":true}',
                                           {"content-type":"application/json"})
```

Esto evita Frida-gadget, objection-patchapk y reFlutter. La app patcheada por `apk-mitm` (cert debug) consulta el flag, recibe truthy del proxy, salta el check, y desde ahí captura mitmproxy todo el flujo con TLS desencriptado.

## Endpoints descubiertos por análisis estático (blutter)

`blutter` extrajo el Object Pool del Dart-AOT (Dart 3.7.2). Hay ~50+ paths del API privado. Todos relativos a `https://rocme.ute.com.uy/customersapp/`.

### Cuentas / clientes
- `customers/profile` — perfil del usuario logueado.
- `customers/setup` — primer setup post-login.
- `customers/loggedin` — confirmar sesión activa.
- `customers/contact`, `customers/contact/verify` — gestión de teléfono/email.
- `customers/event` — eventos de tracking.
- `customers/grant/check` — chequeo de permisos sobre una cuenta (multi-suministro).
- `customers/validate`, `customers/validate/code`, `customers/validate/omit` — validaciones via OTP/SMS.
- `customers/updatefcmtoken` — registrar token Firebase Cloud Messaging para push.

### Suministros / agreements
- `accounts/services/peak` — horario punta del agreement (TRD/TRT).
- `accounts/consumption/simulation` — simulador de consumo.
- `accounts/meters/readsync` — sincronización de lectura del medidor.
- `accounts/miConsumptionCurve/` — curva de consumo (mi-consumo, gráficos).
- `/peak`, `/services`, `/profile`, `/category` — sub-paths de account.

### Consumo y mediciones
- `/activeconsumption/` — energía activa.
- `/reactiveconsumption/` — energía reactiva.
- `/powerconsumption/` — potencia.
- `/consumption/`, `/consumption/daily/`, `/consumption/monthly/` — series temporales.
- `/consumptionevolution/` — comparativa.
- `/calculateConsumptionForPlan/` — what-if con otro plan tarifario.

### Medidor smart / IoT
- `/meters`, `meters/readings` — lecturas crudas del medidor.
- `device/saveprofile` — perfil del device (probablemente de aire/calefón inteligente).
- `device/consumptionBreakdown/` — desglose por dispositivo.
- `device/servicepointtoplan/` — asignación device→plan.
- `device/smartHome/` — config home assistant interno.
- `device/shelly/tokenize/` — vincula medidor Shelly a la cuenta UTE.
- `/poweron`, `/poweroff` — control remoto del relé del medidor.
- `/schedule`, `/schedule/active`, `/schedule/inactive`, `/schedule/bypass` — schedules de encendido/apagado.

### Facturación / pagos / cupones
- `invoices/charts/`, `invoices/file/`, `invoices/totalDebt/`, `invoices/unpaids/` — facturas.
- `invoices/paymentoptions` — métodos de pago disponibles.
- `coupon/check`, `coupon/info`, `coupon/redeem`, `coupon/scan` — sistema de cupones (probable tienda UTE).

### Quality of service / reclamos
- `/status`, `/status/check` — estado del servicio.
- `/quality` — calidad reportada.
- `energyclaims/annul`, `energyclaims/reiterate` — reclamos por incidencias.

### Mensajería / push
- `messages/unread` — count de mensajes pendientes.

### Auth / OIDC
- `/connect/token` — endpoint propio de UTE para canjear el code de id.gub.uy o refresh (lo veremos en captura).
- `/Account/ForgotPassword`, `/Account/Register?returnUrl=` — paths del IdP web.
- `/mobileapp/sign-in`, `/mobileapp/register-success` — sub-paths del App Link redirect.

### Operacionales
- `flags/SecurityChecksBypass` — feature flag (ver bypass arriba).
- `/version/` — chequeo de versión mínima de la app.
- `/check`, `/thirdparty`, `/thirdparty/` — endpoints utility.

> ⚠️ Estos paths salen del Object Pool Dart. **Falta confirmar prefijos exactos, query params, payloads de request y schemas de response** — eso lo da la captura mitm.

## Lo que falta capturar para cerrar v1 del cliente

1. **Headers obligatorios** que UTE exige (probable `X-Client-Type`, version, fingerprint del device).
2. **Formato exacto** del response de `flags/SecurityChecksBypass` (bool plano, `{value:bool}`, etc.).
3. **OAuth flow real**: `client_id`, `redirect_uri`, `scope` en `/authorize`; payload del POST a `/token`; forma de pasar el access_token a `/customersapp/...` (Bearer JWT directo, o intercambio por token UTE).
4. **Códigos de respuesta** de `meters/readsync` (poll status) y de `energyclaims/*` (transiciones).
5. **Schema de `customers/profile`** (campos disponibles para sensores HA).

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
