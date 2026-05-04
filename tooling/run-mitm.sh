#!/bin/bash
# Captura tráfico de la app UTE en el OnePlus 12.
# Uso: ./run-mitm.sh [nombre-de-flow]
#   El OnePlus debe tener proxy WiFi → 192.168.2.10:8080
#   y el cert mitm-ca/mitmproxy-ca-cert.crt instalado como user-CA.

set -euo pipefail

cd "$(dirname "$0")"
NAME="${1:-ute-$(date +%Y%m%d-%H%M%S)}"
OUT="../captures/flows/${NAME}.mitm"
mkdir -p "$(dirname "$OUT")"

echo ">> mitmdump escuchando en 0.0.0.0:8080"
echo ">> guardando flow en: $OUT"
echo ">> filtrando dominio: rocme.ute.com.uy"
echo ">> Ctrl-C para terminar"
echo

# --set confdir apunta al CA local
# --listen-host 0.0.0.0 para que el OnePlus pueda alcanzarlo desde la LAN
# -w guarda el flow file
# --set termlog_verbosity=info para ver requests en la consola
exec uvx --from mitmproxy mitmdump \
  --set confdir="$PWD/mitm-ca" \
  --listen-host 0.0.0.0 \
  --listen-port 8080 \
  -w "$OUT" \
  --set termlog_verbosity=info \
  --set console_eventlog_verbosity=info
