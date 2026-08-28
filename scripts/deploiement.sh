#!/usr/bin/env bash
# Déploiement de la V2 vers le VPS (app.example.org) DEPUIS UN MAC/Unix.
# Équivalent bash de scripts/deploiement.ps1 (Windows). Build SUR le VPS,
# installation hors-ligne (wheels Linux téléchargées en local) — le VPS ne
# contacte jamais PyPI. Voir docs_architecture/08_OPERATIONS_VPS.md et
# 05_DEPLOIEMENT.md.
#
# Prérequis : alias SSH « vps » (~/.ssh/config), uv dans le PATH, python3+pip,
#             ~/stack/app_fdr_v2/.env présent sur le VPS, service fdr2 déclaré
#             dans ~/stack/docker-compose.yml.
#
# Usage :  chmod +x scripts/deploiement.sh  (une fois)
#          ./scripts/deploiement.sh
set -euo pipefail

# 1. Vérification complète AVANT tout transfert (rien ne part sans ça)
echo "--- Vérification (ruff + pyright + pytest) ---"
uv run ruff check app tests scripts
uv run pyright
uv run pytest -q

# 2. Wheels Linux (cp311 manylinux) — pas besoin de Docker sur le Mac
echo "--- Export des dépendances + wheels Linux ---"
uv export --frozen --no-dev --no-emit-project --no-hashes -o requirements.txt
rm -rf wheels && mkdir -p wheels
python3 -m pip download -r requirements.txt -d wheels --only-binary=:all: \
    --python-version 311 --platform manylinux_2_28_x86_64 \
    --platform manylinux_2_17_x86_64 --platform manylinux2014_x86_64 --platform any

# 3. Transfert du code (HEAD : seuls les fichiers commités) + wheels
echo "--- Transfert du code et des wheels ---"
SHA="$(git rev-parse --short HEAD)"
git archive --format=tar -o /tmp/fdr2_deploy.tar HEAD
scp /tmp/fdr2_deploy.tar vps:/tmp/fdr2_deploy.tar
ssh vps "mkdir -p ~/stack/app_fdr_v2 && tar -xf /tmp/fdr2_deploy.tar -C ~/stack/app_fdr_v2 && rm /tmp/fdr2_deploy.tar"
scp -r wheels vps:stack/app_fdr_v2/
# requirements.txt FRAÎCHEMENT généré (étape 2) écrase celui de l'archive : si
# le requirements.txt commité est périmé (deps changées sans régénération), le
# build offline échouerait sinon (cas vécu 2026-06-13).
scp requirements.txt vps:stack/app_fdr_v2/requirements.txt

# 4. SHA de version dans le .env du VPS (exposé par /health) sans toucher au reste
echo "--- Version $SHA ---"
ssh vps "grep -q '^GIT_SHA=' ~/stack/app_fdr_v2/.env \
    && sed -i 's/^GIT_SHA=.*/GIT_SHA=$SHA/' ~/stack/app_fdr_v2/.env \
    || echo 'GIT_SHA=$SHA' >> ~/stack/app_fdr_v2/.env"

# 5. Build hors-ligne + démarrage
echo "--- Build et démarrage sur le VPS ---"
ssh vps "cd ~/stack && docker compose build fdr2 && docker compose up -d fdr2 && docker compose ps fdr2"

# 6. Vérifications post-déploiement — la v1 ne doit JAMAIS être affectée
echo "--- Vérifications ---"
sleep 8
V2="$(curl -s https://app.example.org/health)"
echo "app.example.org/health : $V2 (attendu $SHA)"
echo "$V2" | grep -q "$SHA" || { echo "ERREUR : version inattendue en production"; exit 1; }
echo -n "app-v1.example.org (v1) : "
curl -sI https://app-v1.example.org | head -1
echo "Déploiement terminé."
