#!/usr/bin/env bash
# ==============================================================================
# ArcIA — Lanceur Graphique Universel du Setup Wizard (Linux / macOS)
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Détection de Python 3
PYTHON_BIN=""
if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
else
    echo "ERREUR : Python 3 est requis pour lancer le Wizard ArcIA mais n'a pas été trouvé."
    exit 1
fi

# Exécution du Setup Wizard graphique
exec "$PYTHON_BIN" "${SCRIPT_DIR}/scripts/wizard.py" "$@"
