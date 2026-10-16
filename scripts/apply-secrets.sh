#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
source "$ROOT_DIR/secrets/arcia.env"

echo "[*] Création des Secrets Kubernetes dans le namespace arcia..."

# Secret OpenRouter
kubectl create secret generic enterprise-llm-secret \
  --namespace arcia \
  --from-literal=openrouter-key="$OPENROUTER_API_KEY" \
  --dry-run=client -o yaml | kubectl apply -f -

# Secret Entra ID (utilisé par Open-WebUI et oauth2-proxy)
kubectl create secret generic entraid-secret \
  --namespace arcia \
  --from-literal=client-id="$ENTRA_CLIENT_ID" \
  --from-literal=client-secret="$ENTRA_CLIENT_SECRET" \
  --from-literal=tenant-id="$ENTRA_TENANT_ID" \
  --from-literal=cookie-secret="$OAUTH2_PROXY_COOKIE_SECRET" \
  --dry-run=client -o yaml | kubectl apply -f -

# Secret Hermes Gateway API & Studio
kubectl create secret generic hermes-gateway-secret \
  --namespace arcia \
  --from-literal=api-server-key="$HERMES_API_SERVER_KEY" \
  --from-literal=admin-password="${HERMES_ADMIN_PASSWORD:-admin}" \
  --dry-run=client -o yaml | kubectl apply -f -

# Secret Teams Bot
kubectl create secret generic teams-bot-secret \
  --namespace arcia \
  --from-literal=app-id="$TEAMS_BOT_APP_ID" \
  --from-literal=app-password="$TEAMS_BOT_APP_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -

# Secret Presidio
kubectl create secret generic presidio-secret \
  --namespace arcia \
  --from-literal=master-key="$PRESIDIO_MASTER_KEY" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "[+] Tous les secrets Kubernetes ont été appliqués avec succès."
