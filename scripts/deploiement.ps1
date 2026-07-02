# Déploiement de la V2 vers le VPS (fdr2.revorun.eu) — BUILD SUR LE VPS,
# installation hors-ligne (les wheels Linux sont construites en local : le
# VPS ne contacte jamais PyPI — piège IPv6).
# Prérequis : alias SSH « vps » (OpenSSH Windows, agent chargé), DNS fdr2 posé,
#             ~/stack/app_fdr_v2/.env présent sur le VPS (chmod 600),
#             service fdr2 déclaré dans ~/stack/docker-compose.yml.
# Procédure complète et vérifications : docs_architecture/05_DEPLOIEMENT.md
#
# Usage : powershell -File scripts/deploiement.ps1

$ErrorActionPreference = "Stop"
$ssh = "C:\Windows\System32\OpenSSH\ssh.exe"
$scp = "C:\Windows\System32\OpenSSH\scp.exe"

# uv n'est PAS dans le PATH sur le poste de Victor (installé via pip dans le
# Python système) : on l'invoque toujours par "python -m uv".

# 1. Vérification complète AVANT tout transfert (rien ne part sans ça)
Write-Host "--- Vérification (ruff + pyright + pytest) ---"
python -m uv run ruff check app tests scripts
if ($LASTEXITCODE -ne 0) { throw "ruff a échoué" }
python -m uv run pyright
if ($LASTEXITCODE -ne 0) { throw "pyright a échoué" }
python -m uv run pytest -q
if ($LASTEXITCODE -ne 0) { throw "pytest a échoué" }

# 2. Wheels Linux à jour (uniquement si le lock a changé depuis le dernier export)
Write-Host "--- Export des dépendances + wheels Linux ---"
python -m uv export --frozen --no-dev --no-emit-project --no-hashes -o requirements.txt
if ($LASTEXITCODE -ne 0) { throw "uv export a échoué" }
python -m pip download -r requirements.txt -d wheels --only-binary=:all: `
    --python-version 311 --platform manylinux_2_28_x86_64 `
    --platform manylinux_2_17_x86_64 --platform manylinux2014_x86_64 `
    --platform any --quiet
if ($LASTEXITCODE -ne 0) { throw "pip download a échoué" }

# 3. Archive du code (HEAD : seuls les fichiers commités partent) + wheels
Write-Host "--- Transfert du code et des wheels ---"
$sha = (git rev-parse --short HEAD).Trim()
git archive --format=tar -o "$env:TEMP\fdr2_deploy.tar" HEAD
& $scp "$env:TEMP\fdr2_deploy.tar" vps:/tmp/fdr2_deploy.tar
& $ssh vps "mkdir -p ~/stack/app_fdr_v2/wheels && tar -xf /tmp/fdr2_deploy.tar -C ~/stack/app_fdr_v2 && rm /tmp/fdr2_deploy.tar"
& $scp -r wheels vps:stack/app_fdr_v2/
# requirements.txt FRAÎCHEMENT généré (étape 2) écrase celui de l'archive : si
# le requirements.txt commité est périmé (deps changées sans régénération), le
# build offline échouerait sinon (cas vécu 2026-06-13).
& $scp requirements.txt vps:stack/app_fdr_v2/requirements.txt

# 4. SHA de version dans le .env du VPS (exposé par /health) sans toucher au reste
Write-Host "--- Version $sha ---"
& $ssh vps "grep -q '^GIT_SHA=' ~/stack/app_fdr_v2/.env && sed -i 's/^GIT_SHA=.*/GIT_SHA=$sha/' ~/stack/app_fdr_v2/.env || echo 'GIT_SHA=$sha' >> ~/stack/app_fdr_v2/.env"

# 5. Build hors-ligne + démarrage
Write-Host "--- Build et démarrage sur le VPS ---"
& $ssh vps "cd ~/stack && docker compose build fdr2 && docker compose up -d fdr2 && docker compose ps fdr2"

# 6. Vérifications post-déploiement — la v1 ne doit JAMAIS être affectée
Write-Host "--- Vérifications ---"
Start-Sleep -Seconds 8
$v2 = Invoke-RestMethod https://fdr2.revorun.eu/health
Write-Host "fdr2.revorun.eu/health : version $($v2.version) (attendu $sha)"
if ($v2.version -ne $sha) { throw "Version inattendue en production" }
$v1 = Invoke-WebRequest -UseBasicParsing -Method Head https://fdr.revorun.eu
Write-Host "fdr.revorun.eu (v1) : HTTP $($v1.StatusCode) — toujours en vie"
