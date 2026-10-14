#!/bin/bash
# Prevent recursive re-exec
if [[ -n "$K3S_REEXEC_DONE" ]]; then
    # Run k3s with all config via environment variables, no "server" subcommand
    # This avoids the re-exec loop
    export K3S_CONFIG_FILE="/etc/rancher/k3s/config.yaml"
    export K3S_DATA_DIR="/var/lib/rancher/k3s"
    export K3S_TOKEN_FILE="/etc/rancher/k3s/cluster-token"
    exec -a k3s-server /usr/local/bin/k3s "$@"
fi

export K3S_REEXEC_DONE=1

# Strip "server" if it is the first argument
args=("$@")
if [[ ${args[0]} == "server" ]]; then
    args=("${args[@]:1}")
fi

exec -a k3s-server /usr/local/bin/k3s server "${args[@]}"