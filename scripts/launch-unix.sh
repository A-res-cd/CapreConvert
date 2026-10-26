#!/bin/sh
# CapreConvert source launcher; localraw is the compatible module identifier.
set -eu
project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$project_root"
exec "$project_root/.venv/bin/python" -m localraw "$@"
