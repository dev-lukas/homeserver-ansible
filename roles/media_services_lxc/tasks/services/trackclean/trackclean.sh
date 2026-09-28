#!/bin/sh
# *arr "Import Using Script" entry point. python3/mkvtoolnix come from a docker
# mod at container start; if they are missing, let the *arr do a normal import.
if ! command -v python3 >/dev/null 2>&1 || ! command -v mkvmerge >/dev/null 2>&1; then
    echo "[MoveStatus] DeferMove"
    exit 0
fi
exec python3 "$(dirname "$0")/trackclean.py" "$@"
