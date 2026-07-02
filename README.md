# FNCCR — Cartographie des Usages TCD des Collectivités (V2)

Application web de saisie et de restitution cartographique des projets
« Territoires Connectés Durables ». Reconstruction propre de la v1, à
iso-fonctionnalités et iso-UX/UI. La base de données est un document **Grist**
externe (12 tables `BDD_*`) — aucune base locale.

- Architecture et décisions : [`docs_architecture/`](docs_architecture/)
- Règles pour les contributeurs (humains et IA) : [`AGENTS.md`](AGENTS.md)

## Stack

Python 3.11 · FastAPI · Jinja2 (server-rendered) · pygrister (API Grist) ·
pydantic-settings · uv · ruff · pyright · pytest.

## Installation locale

```bash
# 1. Dépendances (uv crée le venv et installe Python 3.11 si besoin)
uv sync

# 2. Configuration
cp .env.example .env   # puis remplir GRIST_API_KEY, GRIST_DOC_ID, GRIST_SERVER_URL

# 3. Lancer
uv run uvicorn app.main:app --reload
# → http://localhost:8000 (vivacité : GET /health)
```

## Vérification

```bash
uv run ruff check app tests scripts   # lint
uv run pyright                        # typage statique
uv run pytest                         # tests (Grist mocké, aucune donnée réelle)
```

Rien ne part en déploiement sans cette séquence au vert.

## Structure

```
app/
├── main.py            # app FastAPI (fin) : middlewares + routers + lifespan
├── dependencies.py    # fabriques @lru_cache + dépendances d'accès
├── core/              # config (.env), sécurité, flash, templating
├── api/               # routes (fines) — un module par domaine
├── repositories/      # accès Grist : un repository par table, cache TTL,
│                      # erreurs sobres ; les idiomes Grist ne sortent pas d'ici
└── services/          # logique métier
templates/  static/    # UI v1 reprise à l'identique
scripts/               # check_grist_schema, export_grist (sauvegardes)
tests/                 # unit/ + api/ (sécurité : IDOR, CSRF, accès)
```

## Limites assumées (lire avant de « moderniser »)

- **Mono-worker** : cache mémoire, jetons magic link et rate limiting
  supposent un seul process uvicorn. Passer à N workers exige un magasin
  partagé (Redis) pour ces trois mécanismes.
- **Grist sans transactions** : les écritures multi-tables ne sont pas
  atomiques (ordre d'écriture pensé pour minimiser les états incohérents).
- `BDD_Contacts.projet_s_` est un champ texte (nom du projet) — dette v1
  conservée volontairement (iso-fonctionnel).

## Déploiement

`powershell -File scripts/deploiement.ps1` : vérification complète, wheels
Linux téléchargées en local, transfert code + wheels, **build hors-ligne sur
le VPS** (qui ne contacte jamais PyPI — résolveur IPv6 cassé), service `fdr2`
derrière Caddy sur `fdr2.revorun.eu`. Procédure détaillée et vérifications :
[`docs_architecture/05_DEPLOIEMENT.md`](docs_architecture/05_DEPLOIEMENT.md).
La v1 (`fdr.revorun.eu`) n'est jamais touchée.
