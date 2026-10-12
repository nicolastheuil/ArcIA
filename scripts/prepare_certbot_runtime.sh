#!/bin/sh
# User-scoped Certbot; no server or global Python mutation.
set -eu
umask 077
repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
uv="$HOME/.local/share/arcia-toolchain/uv-0.13.0/uv"
runtime="$HOME/.local/share/arcia-certbot"
[ "$("$uv" --version | cut -d ' ' -f 2)" = 0.13.0 ]
if [ ! -e "$runtime" ]; then
    "$uv" --no-config venv --python "$HOME/.local/share/arcia-validation/bin/python" --seed "$runtime"
fi
"$uv" --no-config pip install --python "$runtime/bin/python" --require-hashes \
    -r "$repo_dir/scripts/requirements-certbot.lock.txt"
"$runtime/bin/certbot" --version
