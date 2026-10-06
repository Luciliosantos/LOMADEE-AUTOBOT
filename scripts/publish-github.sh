#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

REPO_NAME="${1:-Lomadee-Auto-Bot}"
OWNER="${2:-}"

if ! command -v git >/dev/null 2>&1; then
  echo "Git não instalado. Instale com: apt-get install -y git"
  exit 1
fi

git init -b main
git add .
git commit -m "feat: initial Lomadee multi-client Telegram bot" || true

echo
echo "Projeto Git pronto."
echo "Se você usa GitHub CLI e já está autenticado:"
echo "  gh repo create $REPO_NAME --private --source=. --remote=origin --push"
echo
echo "Ou crie o repositório no GitHub e depois execute:"
echo "  git remote add origin git@github.com:${OWNER:-SEU_USUARIO}/$REPO_NAME.git"
echo "  git push -u origin main"
