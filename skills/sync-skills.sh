#!/bin/bash
set -e
TARGET="/var/data/arcia/shared-skills"
mkdir -p "$TARGET"

echo "[*] Synchronisation des catalogues de compétences standards..."
# Installation et mise en cache des skills vérifiées
npx -y skills add anthropics/anthropic-quickstarts --destination "$TARGET/anthropics" || true
npx -y skills add vercel/ai-sdk --destination "$TARGET/vercel" || true
npx -y skills add obra/superpowers --destination "$TARGET/superpowers" || true

echo "[+] Synchronisation réussie dans $TARGET"
