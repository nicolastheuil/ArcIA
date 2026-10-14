#!/bin/bash
exec -a k3s-server /usr/local/bin/k3s server "$@"