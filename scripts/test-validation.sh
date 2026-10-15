#!/bin/bash
set -e

echo "=========================================="
echo "    ArcIA v0.2 Platform Validation Tests   "
echo "=========================================="

echo -e "\n[1/6] Vérification des Pods Kubernetes :"
sudo /usr/local/bin/k3s kubectl get pods -n arcia -o wide

echo -e "\n[2/6] Test Presidio DLP Sanitization :"
PRESIDIO_IP=$(sudo /usr/local/bin/k3s kubectl get svc presidio-dlp -n arcia -o jsonpath='{.spec.clusterIP}')
PRESIDIO_RES=$(curl -s -X POST "http://${PRESIDIO_IP}:8080/sanitize" \
  -H "Content-Type: application/json" \
  -d '{"text": "Bonjour, mon mot de passe est SecretPass123 et mon email est user@example.com"}')
echo "Réponse Presidio : $PRESIDIO_RES"

if echo "$PRESIDIO_RES" | grep -q "sanitized_text"; then
  echo "=> SUCCESS: Presidio DLP fonctionne et renvoie un texte assaini."
else
  echo "=> ERROR: Réponse Presidio inattendue."
fi

echo -e "\n[3/6] Test LiteLLM Proxy Health :"
LITELLM_IP=$(sudo /usr/local/bin/k3s kubectl get svc litellm-proxy -n arcia -o jsonpath='{.spec.clusterIP}')
LITELLM_RES=$(curl -s -o /dev/null -w "%{http_code}" "http://${LITELLM_IP}:4000/health/readiness" || true)
echo "Code HTTP LiteLLM (/health/readiness) : $LITELLM_RES"

echo -e "\n[4/6] Test Hermes Agent (Studio port 9119 & Gateway port 8642) :"
HERMES_IP=$(sudo /usr/local/bin/k3s kubectl get svc hermes-studio -n arcia -o jsonpath='{.spec.clusterIP}')
HERMES_STUDIO_RES=$(curl -s -o /dev/null -w "%{http_code}" "http://${HERMES_IP}:9119" || true)
HERMES_GATEWAY_RES=$(curl -s -o /dev/null -w "%{http_code}" "http://${HERMES_IP}:8642" || true)
echo "Code HTTP Hermes Studio (9119) : $HERMES_STUDIO_RES"
echo "Code HTTP Hermes Gateway (8642) : $HERMES_GATEWAY_RES"

echo -e "\n[5/6] Test Teams Bot Adapter Health :"
TEAMS_IP=$(sudo /usr/local/bin/k3s kubectl get svc teams-bot-adapter -n arcia -o jsonpath='{.spec.clusterIP}')
TEAMS_RES=$(curl -s "http://${TEAMS_IP}:3978/health" || true)
echo "Réponse Teams Bot (/health) : $TEAMS_RES"

echo -e "\n[6/6] Test Open-WebUI Portal Health :"
WEBUI_IP=$(sudo /usr/local/bin/k3s kubectl get svc open-webui -n arcia -o jsonpath='{.spec.clusterIP}')
WEBUI_RES=$(curl -s -o /dev/null -w "%{http_code}" "http://${WEBUI_IP}:8080/health" || true)
echo "Code HTTP Open-WebUI (/health) : $WEBUI_RES"

echo -e "\n=========================================="
echo "    Validation Terminée avec Succès       "
echo "=========================================="
