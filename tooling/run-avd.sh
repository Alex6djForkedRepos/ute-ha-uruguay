#!/bin/bash
# Bootea el AVD con proxy hardcoded a mitmproxy y system writable
# (para poder instalar el cert mitm como system CA).
#
# Pre-req:
#   - $ANDROID_HOME apuntando a tooling/android-sdk
#   - AVD `ute_capture` ya creado (run create-avd.sh primero)
#   - mitmdump corriendo en 192.168.2.10:8080 (run-mitm.sh)
set -euo pipefail

THIS_DIR="$(cd "$(dirname "$0")" && pwd)"
export ANDROID_HOME="$THIS_DIR/android-sdk"
export ANDROID_SDK_ROOT="$ANDROID_HOME"
export PATH="$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator:$PATH"

PROXY_HOST="${PROXY_HOST:-192.168.2.10}"
PROXY_PORT="${PROXY_PORT:-8080}"
AVD_NAME="${AVD_NAME:-ute_capture}"

echo ">> launching $AVD_NAME with HTTP proxy $PROXY_HOST:$PROXY_PORT"

# -no-snapshot-load: arranque limpio cada vez (-no-snapshot guarda al apagar)
# -writable-system: /system rw para sideloadear cert mitm
# -http-proxy: el qemu enforces este proxy a TODO TCP (Flutter no puede esquivarlo)
# -dns-server: evita DoH y otros bypass
# -no-boot-anim: arranque más rápido
# -no-audio: sin sonido
exec emulator \
  -avd "$AVD_NAME" \
  -no-snapshot-load \
  -writable-system \
  -http-proxy "http://$PROXY_HOST:$PROXY_PORT" \
  -no-boot-anim \
  -no-audio \
  -gpu swiftshader_indirect \
  -accel on
