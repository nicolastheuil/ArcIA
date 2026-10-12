#!/bin/sh
# User-scoped controller runtime. uv release and embedded Python download catalog pinned.
set -eu
umask 077
[ "$(uname -m)" = x86_64 ] || { printf '%s\n' WSL_AMD64_REQUIRED; exit 2; }
toolchain="$HOME/.local/share/arcia-toolchain"
validation="$HOME/.local/share/arcia-validation"
mkdir -p "$toolchain"
archive="$toolchain/uv-0.13.0-x86_64-unknown-linux-gnu.tar.gz"
if [ ! -f "$archive" ]; then
    curl --fail --location --proto '=https' --tlsv1.2 \
        'https://github.com/astral-sh/uv/releases/download/0.13.0/uv-x86_64-unknown-linux-gnu.tar.gz' \
        --output "$archive"
fi
printf '%s  %s\n' '1468ebd5a5541121837c5a2817b9972ba6090fa6caa3d142620850a47fb75154' "$archive" | sha256sum --check --status
if [ ! -d "$toolchain/uv-0.13.0" ]; then
    mkdir "$toolchain/uv-0.13.0"
    tar -xzf "$archive" -C "$toolchain/uv-0.13.0" --strip-components=1
fi
uv="$toolchain/uv-0.13.0/uv"
[ "$("$uv" --version | cut -d ' ' -f 2)" = 0.13.0 ]
export UV_PYTHON_INSTALL_DIR="$toolchain/python"
export UV_CACHE_DIR="$toolchain/cache"
if [ ! -e "$validation" ]; then
    "$uv" --no-config venv --python 3.14.7 --seed "$validation"
fi
"$validation/bin/python" -c 'import sys,ssl,venv; assert sys.version_info[:2] >= (3,12); print("WSL_CONTROLLER_PYTHON_READY")'
