"""
mitmproxy addon: intercept `GET /customersapp/flags/SecurityChecksBypass`
y devolver true para que la app UTE patcheada arranque sin que su
integrity check Dart-side cierre la actividad.

Uso:
  ./tooling/run-mitm.sh ute-bypass    (corre mitmdump con este addon ya cargado)

NOTA: la app llama a un endpoint privado de UTE. Como no sabemos el formato
exacto de la respuesta, devolvemos varios shapes a la vez (es JSON, los campos
extra los ignora Dart). Si la app sigue cerrándose, ajustar `_truthy_payloads`.
"""
from mitmproxy import http
import json


_truthy_payloads = [
    # shapes posibles ordenados por probabilidad
    {"value": True, "data": True, "result": True, "success": True, "enabled": True},
]

# variantes para body=true sin envoltorio
_truthy_raw = "true"


class SecurityChecksBypass:
    """Devuelve siempre true al flag para que la app no chequee tamper."""

    def request(self, flow: http.HTTPFlow) -> None:
        if "rocme.ute.com.uy" not in flow.request.host:
            return
        if "/flags/SecurityChecksBypass" not in flow.request.path:
            return
        # corto el request, respondo sin pasar por el server
        flow.response = http.Response.make(
            200,
            json.dumps(_truthy_payloads[0]).encode("utf-8"),
            {"content-type": "application/json; charset=utf-8"},
        )

    def response(self, flow: http.HTTPFlow) -> None:
        # Por si llegó al backend (no debería con request() activo).
        # Sobrescribimos para garantizar el bypass.
        if "rocme.ute.com.uy" not in flow.request.host:
            return
        if "/flags/SecurityChecksBypass" not in flow.request.path:
            return
        flow.response.status_code = 200
        flow.response.headers["content-type"] = "application/json; charset=utf-8"
        flow.response.set_text(json.dumps(_truthy_payloads[0]))


addons = [SecurityChecksBypass()]
