#!/bin/sh
set -eu
umask 077
repo_dir=$1
uv="$HOME/.local/share/arcia-toolchain/uv-0.13.0/uv"
runtime="$HOME/.local/share/arcia-builder/python"
[ "$("$uv" --version | cut -d ' ' -f 2)" = 0.13.0 ]
mkdir -p "$HOME/.local/share/arcia-builder"
if [ ! -e "$runtime" ]; then
    "$uv" --no-config venv --python "$HOME/.local/share/arcia-validation/bin/python" "$runtime"
fi
"$uv" --no-config pip install --python "$runtime/bin/python" --require-hashes \
    -r "$repo_dir/builder/requirements-tools.lock.txt"
"$runtime/bin/lintlang" --version
