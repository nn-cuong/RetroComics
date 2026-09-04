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
# 1. Bundled Python in App (Matches RetroRead identical environment)
if [ -f "$APP_DIR/python/bin/python3" ]; then
    PY="$APP_DIR/python/bin/python3"
    export PYTHONHOME="$APP_DIR/python"
    export PYTHONPATH="$APP_DIR/python/lib/python3.11:$APP_DIR/vendor:$APP_DIR"
elif [ -x "/usr/bin/python3" ]; then
    PY="/usr/bin/python3"
    export PYTHONPATH="$APP_DIR/vendor:$APP_DIR:$PYTHONPATH"
elif [ -x "/mnt/SDCARD/System/bin/python3" ]; then
    PY="/mnt/SDCARD/System/bin/python3"
    export PYTHONPATH="$APP_DIR/vendor:$APP_DIR:$PYTHONPATH"
elif command -v python3 >/dev/null 2>&1; then
    PY="$(command -v python3)"
    export PYTHONPATH="$APP_DIR/vendor:$APP_DIR:$PYTHONPATH"
fi

# Cap CPU max frequency to 1008MHz (plenty for comics/manga, prevents thermal build-up)
echo ondemand > /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null
echo 408000 > /sys/devices/system/cpu/cpu0/cpufreq/scaling_min_freq 2>/dev/null
echo 1008000 > /sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq 2>/dev/null

restore_cpu() {
    echo ondemand > /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null
    echo 2000000 > /sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq 2>/dev/null
}
trap restore_cpu EXIT INT TERM

if [ -z "$PY" ]; then
    echo "Cannot find a valid Python3 interpreter" > "$APP_DIR/crash.log"
    exit 1
fi

"$PY" main.py > "$APP_DIR/crash.log" 2>&1
EXIT_CODE=$?

restore_cpu
exit $EXIT_CODE


