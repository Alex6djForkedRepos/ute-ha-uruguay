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


# Schema real observado en captura: {"active": <bool>}.
_TRUTHY = {"active": True}


def _is_target(flow: http.HTTPFlow) -> bool:
    # pretty_host usa el Host header / SNI, NO la IP destino.
    host = flow.request.pretty_host or flow.request.host
    if "rocme.ute.com.uy" not in host:
        return False
    return "/flags/SecurityChecksBypass" in flow.request.path


class SecurityChecksBypass:
    """Forzar 'active: true' al flag para que la app no aborte por
    emulator/tampered/compromised."""

    def request(self, flow: http.HTTPFlow) -> None:
        if not _is_target(flow):
            return
        flow.response = http.Response.make(
            200,
            json.dumps(_TRUTHY).encode("utf-8"),
            {"content-type": "application/json; charset=utf-8"},
        )

    def response(self, flow: http.HTTPFlow) -> None:
        if not _is_target(flow):
            return
        flow.response.status_code = 200
        flow.response.headers["content-type"] = "application/json; charset=utf-8"
        flow.response.set_text(json.dumps(_TRUTHY))


addons = [SecurityChecksBypass()]
