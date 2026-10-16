#!/bin/bash
set -e

# ==============================================================================
# ArcIA — Synchronisation et Mise à Jour des Compétences (Skills)
# ==============================================================================
# Usage :
#   bash skills/sync-skills.sh               # Synchronisation initiale
#   bash skills/sync-skills.sh --update      # Mise à jour des dépôts existants
#   bash skills/sync-skills.sh --local-only  # Synchronisation des skills locales uniquement
# ==============================================================================

TARGET="${ARCIA_SKILLS_DIR:-/var/data/arcia/shared-skills}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DO_UPDATE=false
LOCAL_ONLY=false

for arg in "$@"; do
  case "$arg" in
    --update|-u)
      DO_UPDATE=true
      ;;
    --local-only|--offline|-l)
      LOCAL_ONLY=true
      ;;
  esac
done

echo "=============================================================================="
echo " ArcIA — Synchronisation des Compétences Partagées (Skills)"
echo " Cible : $TARGET"
echo "=============================================================================="

mkdir -p "$TARGET"

# 1. Synchronisation des Compétences Natives ArcIA (Toujours prioritaire et offline)
echo "[*] Synchronisation des compétences natives ArcIA..."
mkdir -p "$TARGET/arcia"
for skill_dir in "$SCRIPT_DIR"/*/; do
  if [ -d "$skill_dir" ]; then
    skill_name="$(basename "$skill_dir")"
    if [ "$skill_name" != "node_modules" ]; then
      mkdir -p "$TARGET/arcia/$skill_name"
      cp -r "$skill_dir"* "$TARGET/arcia/$skill_name/" 2>/dev/null || true
      echo "  [+] Compétence native installée : arcia/$skill_name"
    fi
  fi
done

# 2. Synchronisation des Catalogues Standards Externes (si non --local-only)
if [ "$LOCAL_ONLY" = false ]; then
  echo "[*] Synchronisation des catalogues de compétences communautaires..."

  # Helper d'installation / mise à jour
  sync_catalog() {
    local repo="$1"
    local dest_name="$2"
    local dest_dir="$TARGET/$dest_name"

    if [ -d "$dest_dir" ] && [ "$DO_UPDATE" = true ]; then
      echo "  [~] Mise à jour du catalogue : $repo -> $dest_name"
      if command -v skills >/dev/null 2>&1; then
        skills update "$repo" --destination "$dest_dir" 2>/dev/null || true
      elif command -v npx >/dev/null 2>&1; then
        npx -y skills add "$repo" --destination "$dest_dir" --force 2>/dev/null || true
      fi
    elif [ ! -d "$dest_dir" ]; then
      echo "  [+] Téléchargement du catalogue : $repo -> $dest_name"
      if command -v skills >/dev/null 2>&1; then
        skills add "$repo" --destination "$dest_dir" 2>/dev/null || true
      elif command -v npx >/dev/null 2>&1; then
        npx -y skills add "$repo" --destination "$dest_dir" 2>/dev/null || true
      fi
    else
      echo "  [=] Catalogue déjà présent : $dest_name (utilisez --update pour actualiser)"
    fi
  }

  sync_catalog "affaan-m/everything-claude-code" "ecc"
  sync_catalog "obra/superpowers" "superpowers"
  sync_catalog "vercel/ai-sdk" "vercel"
  sync_catalog "anthropics/anthropic-quickstarts" "anthropics"
else
  echo "[*] Mode local-only activé : Catalogues externes ignorés."
fi

# 3. Génération du Rapport d'Indexation Local
SKILL_COUNT=$(find "$TARGET" -name "SKILL.md" 2>/dev/null | wc -l || echo 0)
echo "=============================================================================="
echo "[+] Synchronisation réussie dans $TARGET"
echo "[+] Nombre total de compétences opérationnelles : $SKILL_COUNT"
echo "=============================================================================="
