#!/bin/bash
args=("$@")
if [[ ${args[0]} == "agent" ]]; then
    args=("${args[@]:1}")
fi
exec -a k3s-agent /usr/local/bin/k3s agent "${args[@]}"