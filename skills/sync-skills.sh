#!/bin/bash
set -e
TARGET="/var/data/arcia/shared-skills"
mkdir -p "$TARGET"

echo "[*] Synchronisation des catalogues de compétences standards..."
# Installation et mise en cache des skills vérifiées
npx -y skills add anthropics/anthropic-quickstarts --destination "$TARGET/anthropics" || true
npx -y skills add vercel/ai-sdk --destination "$TARGET/vercel" || true
npx -y skills add obra/superpowers --destination "$TARGET/superpowers" || true

echo "[*] Synchronisation des compétences locales ArcIA..."
mkdir -p "$TARGET/arcia"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for skill_dir in "$SCRIPT_DIR"/*/; do
  if [ -d "$skill_dir" ]; then
    skill_name="$(basename "$skill_dir")"
    mkdir -p "$TARGET/arcia/$skill_name"
    cp -r "$skill_dir"* "$TARGET/arcia/$skill_name/" 2>/dev/null || true
  fi
done

echo "[+] Synchronisation réussie dans $TARGET"
