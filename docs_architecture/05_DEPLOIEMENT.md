# Déploiement — fdr2.revorun.eu (v1 intacte)

> **MÉTHODE EN VIGUEUR : image construite par GitHub Actions et publiée dans
> GHCR.** Le workflow `.github/workflows/docker-release.yml` construit les
> architectures `amd64` et `arm64`, publie `staging` depuis `main` et les tags
> semver depuis les tags `vX.Y.Z`. Le VPS ne construit donc plus l'image et ne
> contacte jamais PyPI.

Conforme à `KIT_REBUILD_V2/VPS_DEPLOY.md`. Règles absolues : ne jamais toucher au service
`fdr`, ne jamais exposer de port public supplémentaire, jamais de `docker compose down -v`.

## Séquence

1. **Avant tout** : Victor crée le DNS A `fdr2.revorun.eu` → `<IP_DU_VPS>`
   (avant le premier `up`, pour que le certificat Let's Encrypt s'émette du premier coup).
   **Et** : export daté du document Grist (voir `03` §4) avant l'ouverture au public.

2. **Vérification + wheels en local** (sur le poste, réseau sain — pas besoin
   de Docker) :
   ```powershell
   python -m uv run ruff check app tests scripts   # rien ne part sans ça (R2)
   python -m uv run pyright
   python -m uv run pytest -q
   python -m uv export --frozen --no-dev --no-emit-project --no-hashes -o requirements.txt
   python -m pip download -r requirements.txt -d wheels --only-binary=:all: `
       --python-version 311 --platform manylinux_2_28_x86_64 `
       --platform manylinux_2_17_x86_64 --platform manylinux2014_x86_64 --platform any
   ```

3. **Livraison du code + des wheels** (le VPS n'a pas accès au dépôt) :
   ```powershell
   git archive --format=tar -o $env:TEMP\fdr2_deploy.tar HEAD
   scp.exe $env:TEMP\fdr2_deploy.tar vps:/tmp/
   ssh.exe vps "mkdir -p ~/stack/app_fdr_v2 && tar -xf /tmp/fdr2_deploy.tar -C ~/stack/app_fdr_v2"
   scp.exe -r wheels vps:stack/app_fdr_v2/
   ```
   (ssh/scp de `C:\Windows\System32\OpenSSH\`, pas celui de Git-bash.
   `git archive HEAD` : seuls les fichiers COMMITÉS partent.)

4. **`.env` sur le VPS** (`~/stack/app_fdr_v2/.env`, chmod 600) :
   - `GRIST_API_KEY` + `GRIST_DOC_ID` repris de `~/stack/app_form_fnccr/.env` (mêmes données ;
     à terme : compte de service dédié, voir `03` §4) ;
   - **NOUVELLE** `SECRET_KEY` générée pour la V2 ;
   - `ENVIRONMENT=production` ;
   - `APP_PUBLIC_URL=https://fdr2.revorun.eu` ;
   - variables SMTP pour notifications admin si utilisées : `SMTP_HOST/PORT/USER/
     PASSWORD/FROM` ;
   - (plus tard) variables OIDC : `OIDC_ISSUER`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`.

5. **Intégration au stack — ajouts uniquement, aucune ligne existante modifiée.**
   FAIT le 2026-06-12 (sauvegardes datées `*.bak-…-pre-fdr2` créées avant).
   Stanza EFFECTIVE dans `~/stack/docker-compose.yml` (insérée avant la
   section top-level `networks:`) :
     ```yaml
     fdr2:
       build: ./app_fdr_v2          # build SUR le VPS, hors-ligne (wheels/)
       container_name: fdr2
       restart: unless-stopped
       env_file: ./app_fdr_v2/.env
       mem_limit: 512m              # D4 : ne jamais pouvoir affamer la v1
       cpus: "1.0"
       logging:
         driver: json-file
         options:
           max-size: "10m"
           max-file: "3"
       networks:
         - stack                    # le réseau nommé du stack (celui de Caddy)
       # pas de "ports:" → accessible uniquement par Caddy via le réseau interne
     ```
   - `~/stack/Caddyfile` :
     ```caddyfile
     fdr2.revorun.eu {
         import security_headers
         reverse_proxy fdr2:8000
         encode gzip
     }
     ```
     Vérifier au préalable le contenu du snippet `security_headers` (répartition des
     headers, voir `03` §2-S6 : HSTS à Caddy, CSP à l'app).

6. **Pull de l'image + démarrage** :
   ```bash
  ssh.exe vps "cd ~/stack/app_fdr_v2 && docker compose -f docker-compose.yml -f docker-compose.prod.yml pull app && docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d app"
   ```
  Le tag est `staging` par défaut (`FDR_APP_TAG` permet de choisir une version
  semver). Le `GIT_SHA` est intégré à l'image par le workflow et c'est lui que
  `/health` expose.

7. **Vérifications post-déploiement** :
   ```bash
  ssh.exe vps "cd ~/stack/app_fdr_v2 && docker compose -f docker-compose.yml -f docker-compose.prod.yml ps app && docker compose -f docker-compose.yml -f docker-compose.prod.yml logs app --tail 20"
   curl -s https://fdr2.revorun.eu/health   # 200 + SHA attendu → LA BONNE version répond (R1)
   curl -I https://fdr.revorun.eu           # la v1 doit TOUJOURS répondre
   ```
  - test de bout en bout du SSO (redirection IdP puis retour callback).

8. **Rollback** : `docker compose stop fdr2` — la v1 n'est jamais dans le chemin. Pour
   revenir à une version antérieure : `git checkout <sha>` en local puis redéployer
   (le build est reproductible : wheels + requirements.txt versionné). La bascule
   finale fdr → fdr2 (si souhaitée un jour) sera un chantier séparé décidé par Victor.

## Image Docker

- `python:3.11-slim`, utilisateur **non-root**, `EXPOSE 8000` (jamais publié publiquement).
- Version applicative : variable d'env `GIT_SHA` (écrite dans le `.env` du VPS à chaque
  déploiement), exposée par `/health` (traçabilité R1).
- **`HEALTHCHECK` sans I/O externe** (D3) : `/health` ne touche ni Grist ni api-adresse
  (sinon une panne amont déclencherait des redémarrages en boucle d'une app saine) ;
  la sonde utilise `python -c "urllib.request..."` car `slim` n'embarque pas curl.
- `CMD` uvicorn : `--proxy-headers --forwarded-allow-ips=*` (réseau interne docker — S3),
  **sans `--workers`** (mono-worker = invariant : cache mémoire, jetons consommés, rate
  limiting — D6 ; documenté dans AGENTS.md et README).
- Dépendances : `pip install --no-index --find-links=wheels/ -r requirements.txt` —
  100 % hors-ligne sur le VPS (les wheels cp311 manylinux sont compatibles avec la
  glibc de bookworm).
- Reconstruction périodique de l'image de base pour récupérer les correctifs de
  `python:3.11-slim` + audit des dépendances (`pip-audit` sur requirements.txt) — R2.
