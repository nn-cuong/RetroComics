#!/bin/sh
case "$0" in
    */*) cd "${0%/*}" || exit 1 ;;
esac
APP_DIR="$(pwd)"

# Grant permissions only if needed
[ -x "$APP_DIR/python/bin/python3" ] || chmod +x "$APP_DIR/python/bin/"* "$APP_DIR/bin/"* 2>/dev/null

# Non-blocking extraction tools staging (Only copy once per reboot session in background)
if [ ! -f /tmp/7zzs ] && [ -f "$APP_DIR/bin/7zzs" ]; then
    (cp -f "$APP_DIR/bin/7zzs" /tmp/7zzs 2>/dev/null && chmod +x /tmp/7zzs 2>/dev/null) &
fi
if [ ! -f /tmp/unrar ] && [ -f "$APP_DIR/bin/unrar" ]; then
    (cp -f "$APP_DIR/bin/unrar" /tmp/unrar 2>/dev/null && chmod +x /tmp/unrar 2>/dev/null) &
fi

export LD_LIBRARY_PATH="$APP_DIR/python/lib:$APP_DIR/vendor/pypdfium2_raw:$APP_DIR/bin:$APP_DIR:$LD_LIBRARY_PATH:/usr/trimui/lib:/mnt/SDCARD/System/lib"
export PYSDL2_DLL_PATH="/usr/trimui/lib"
export SDL_NOMOUSE=1

cd "$APP_DIR"

PY=""
# 1. Bundled Python in App (Direct Instant Boot - 0ms probe overhead)
if [ -f "$APP_DIR/python/bin/python3" ]; then
    PY="$APP_DIR/python/bin/python3"
    export PYTHONHOME="$APP_DIR/python"
    export PYTHONPATH="$APP_DIR/python/lib/python3.11:$APP_DIR/vendor:$APP_DIR"
elif [ -f "/mnt/SDCARD/System/bin/python3" ]; then
    PY="/mnt/SDCARD/System/bin/python3"
elif [ -f "/usr/bin/python3" ]; then
    PY="/usr/bin/python3"
else
    PY=$(command -v python3)
fi

if [ -z "$PY" ]; then
    echo "Cannot find a valid Python3 interpreter" > "$APP_DIR/crash.log"
    exit 1
fi

exec "$PY" main.py > "$APP_DIR/crash.log" 2>&1


