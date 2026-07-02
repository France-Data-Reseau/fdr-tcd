# Architecture technique

> Révisé suite aux revues du 2026-06-12 (`revues/`) : ownership étendu aux lectures (B2),
> contrainte mono-worker explicitée (D6), règles d'étanchéité des couches, livraison par
> image Docker (B1 — voir `05_DEPLOIEMENT.md`).

## 1. Vue d'ensemble — couches

Architecture en couches, à étanchéité stricte :

```
Routes (fines, app/api/) → Services (logique métier) → Repositories (1 par table Grist, pygrister)
Schemas Pydantic (validation formulaires, services/types.py) | Core (config, sécurité, templates)
```

- **Routes** (`app/api/`) : extraction du formulaire → modèle Pydantic → appel service →
  redirect 303 + flash. Zéro logique métier. Fonctions `def` synchrones (threadpool FastAPI)
  — exception : la restitution est `async def` (elle
  parallélise les lectures via `asyncio.to_thread` + `gather`).
- **Services** (`app/services/`) : règles métier — agrégation restitution, liaisons RefList,
  workflow de validation des comptes, géo-résolution, magic links.
- **Repositories** (`app/repositories/`) : un par table `BDD_*`, pattern repository classique —
  `Protocol` + implémentation `Grist*Repository(GristApi)`, retours `(status, data)` vérifiés,
  TypedDicts dans `types.py`. Seule couche qui connaît les noms de colonnes Grist.
- **Core** (`app/core/`) : config pydantic-settings, sécurité (CSRF, headers, sessions),
  flash, environnement Jinja2.
- **Injection** (`app/dependencies.py`) : fabriques `get_*_repository()` / `get_*_service()`
  en `@lru_cache` + dépendances d'accès (`require_auth` / `require_editor` / `require_admin`
  / `require_ownership`).

**Règles d'étanchéité et invariants** (inscrits dans `AGENTS.md` pour survivre aux sessions
futures) :
1. Les idiomes pygrister/Grist — tuples `(status, data)`, listes `['L', id…]` — ne remontent
   **jamais** au-dessus des repositories. Si les services les manipulent, l'abstraction est
   percée et un éventuel remplacement de Grist coûtera le double.
2. L'**invalidation du cache vit dans les méthodes d'écriture de `repositories/base.py`**,
   pas dans les services — sinon chaque nouveau POST est une occasion de l'oublier (bug
   « données périmées 5 min » très coûteux à diagnostiquer).
3. **Grist n'a pas de transactions** : une création multi-tables (projet + liaisons) peut
   échouer à mi-chemin. Les services écrivent dans un ordre qui minimise les états
   incohérents (sous-objets/liaisons d'abord ou parent d'abord selon le sens des références)
   et journalisent l'état atteint en cas d'échec partiel.
4. **Mono-worker = invariant** (D6) : cache mémoire, magasin des jetons magic link consommés
   et compteurs slowapi reposent sur « 1 process ». `CMD` uvicorn sans `--workers` ; passer
   à N workers imposerait un magasin partagé (Redis) pour ces trois mécanismes.
5. `require_ownership` s'applique aux routes paramétrées de complétion **en lecture (GET)
   comme en écriture (POST)** pour les Éditeurs (B2) ; hors périmètre → **404**.

## 2. Choix techniques justifiés

| Sujet | Choix | Justification |
|---|---|---|
| Framework | FastAPI + Jinja2 + uvicorn (Python 3.11) | Iso-v1 : templates réutilisés tels quels. |
| Client Grist | **pygrister 0.9.x** | Choix de Victor ; pattern repository éprouvé. Synchrone : compensé (voir Performance). `requests.Session` injectée pour timeouts + retries bornés. |
| Config | pydantic-settings (`core/config.py`) | Tout en `.env`, y compris l'URL Grist (en dur dans la v1 — corrigé). **Refus de démarrer en prod sans `SECRET_KEY`**. |
| Validation | Pydantic v2, un modèle par formulaire (`services/types.py`) | Types, longueurs max, emails/URLs valides, listes d'IDs entiers (faiblesse v1 n°4). |
| Cache | TTL mémoire 5 min, 2 niveaux : (a) tables de référence + choix `widgetOptions` ; (b) payload restitution dérivé. **Invalidation ciblée par table** après écriture | La v1 rechargeait TOUT le cache après chaque POST. 1 worker uvicorn → pas besoin de Redis. |
| Performance | Routes sync en threadpool ; restitution : lectures enveloppées dans `asyncio.to_thread` + `gather` (8 tables en parallèle) ; index `id → record` en mémoire ; coordonnées lues depuis Grist | Pas de N+1 ; échelle réelle : ~260 collectivités, 154 projets. **Risque accepté** (revue Gemini) : sous forte charge, le threadpool peut saturer (GIL + désérialisation JSON) ; surveiller les temps de réponse de `/restitution` — l'issue de secours est un client httpx async derrière les mêmes Protocols, sans toucher aux services. |
| Anti-IDOR | Dépendance centralisée `require_ownership` sur TOUTE route paramétrée de complétion — **lectures GET comprises** (B2) ; hors périmètre → 404 | Faiblesse v1 n°3 : contrôle au cas par cas → généralisé. Les pages de complétion affichent les contacts (emails/téléphones) : sans contrôle des GET, l'énumération d'IDs reconstituerait l'annuaire. |
| Rate limiting | slowapi : login, inscription, demande d'élévation, envoi de magic link (par IP + par email), API restitution (modéré). Uvicorn `--proxy-headers --forwarded-allow-ips` + key function sur l'IP transmise (S3 — sinon limites globales derrière Caddy) | Faiblesse v1 n°1. |
| Lint/typage | ruff + pyright + pre-commit | Critère d'acceptation. |
| Docker | python:3.11-slim, non-root, `HEALTHCHECK` sans I/O externe (sonde `python -c`, slim n'a pas curl), `ARG GIT_SHA` exposé par `/health`, CMD mono-worker + `--proxy-headers`. **Livraison par image** (`docker save`/`load`) — build local, jamais sur le VPS | Corrige B1 (plan wheels incohérent) ; le piège PyPI/IPv6 disparaît du chemin critique ; ce qui tourne = ce qui a été testé. |
| Géocodage | Logique `geo_resolver` v1 conservée à l'identique ; départements injectés depuis `BDD_Departements` (le module `data_lists` v1 codé en dur disparaît) ; httpx async + sémaphore, timeout 10 s | Coordonnées stockées dans Grist en priorité ; on ne géocode que les nouveaux cas ; échec géocodage ≠ échec de page. |

**Pièges Grist intégrés** (BRIEF §5) : batching PATCH à champs homogènes avec repli unitaire
(n°2) ; helpers `ref_ids`/`to_reflist` `['L', id…]` (n°3) ; champs formule jamais écrits (n°5) ;
extraction tolérante listes/scalaires (n°6) ; choix lus depuis `widgetOptions` (n°7) ;
toute éventuelle migration de schéma passerait par l'API, jamais l'interface (n°1).

**Assainissements sans impact visuel** (templates par ailleurs repris tels quels) :
1. **Tout** le JS inline est externalisé — inventaire réel (S7) : `restitution.html` (2 blocs,
   ~35 Ko) → `static/js/restitution.js` ; `base.html`, `accueil.html`, `cas_usage.html`
   (1 bloc + 1 handler `onclick`) → `static/js/app.js`. Comportement identique, et la CSP
   peut alors interdire `unsafe-inline` pour les scripts.
2. Leaflet 1.9.4 auto-hébergé dans `static/vendor/` (plus de CDN unpkg) ; les **tuiles**
   restent servies par OpenStreetMap (comme en v1) → autorisé dans `img-src`.
3. `scripts/check_grist_schema.py` est aussi exécuté **au démarrage de l'app** (lifespan) :
   si le schéma Grist réel diverge de `SCHEMA_GRIST.md`, log CRITICAL immédiat — on ne
   découvre pas une colonne renommée via les retours utilisateurs (revue Gemini).

## 3. Liste exhaustive des fichiers

```
app_fdr_v2/
├── pyproject.toml               — deps prod+dev (uv), config ruff/pytest
├── uv.lock                      — versions verrouillées
├── .python-version              — 3.11
├── .pre-commit-config.yaml      — ruff + pyright avant commit
├── pyrightconfig.json           — typage statique sur app/
├── .env.example                 — toutes les variables documentées, zéro secret
├── .gitignore / .dockerignore   — .env, caches, kit exclus
├── README.md                    — installation, structure, exploitation, déploiement, limites
│                                  assumées (mono-worker, couplage Grist, pas de transactions)
├── AGENTS.md                    — règles projet pour les sessions futures : étanchéité des
│                                  couches, invalidation cache dans base.py, mono-worker,
│                                  « Extention » = valeur de données à ne pas corriger
├── Dockerfile                   — slim, non-root, healthcheck python -c (sans I/O externe),
│                                  ARG GIT_SHA, CMD mono-worker + --proxy-headers
│
├── app/
│   ├── __init__.py
│   ├── main.py                  — logging + app FastAPI + middlewares + include_router (fin) ;
│   │                              lifespan : vérification du schéma Grist (CRITICAL si divergence)
│   ├── dependencies.py          — fabriques @lru_cache (settings, repos, services) + dépendances
│   │                              d'accès : require_auth / require_editor / require_admin / require_ownership
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py            — Settings pydantic-settings ; refus de démarrer en prod sans
│   │   │                          SECRET_KEY NI SMTP_* (vital pour l'auth)
│   │   ├── security.py          — middleware headers (CSP stricte, X-Content-Type-Options,
│   │   │                          Referrer-Policy — HSTS laissé à Caddy), CSRF, helpers session
│   │   │                          (identité seule, rôle re-résolu à chaque requête), key function
│   │   │                          rate-limit (IP transmise par le proxy), salts signés distincts
│   │   ├── flash.py             — messages flash en session (succès/erreur)
│   │   └── templating.py        — env Jinja2 (autoescape) + globals v1 (grist_field, ref_ids_of, csrf)
│   ├── api/
│   │   ├── __init__.py
│   │   ├── auth.py              — /login (envoi magic link), /auth/verifier (GET = page de
│   │   │                          confirmation sans effet de bord, POST = consommation + session),
│   │   │                          /inscription, /acces-refuse, /logout, /demande-modification
│   │   ├── menu.py              — / (tuiles par rôle, pastille « En attente ») + /health
│   │   ├── admin.py             — /admin (console) + POST /admin/utilisateur/{id}
│   │   ├── completion.py        — /completion (Éditeur → redirigé sur SA collectivité)
│   │   ├── collectivites.py     — GET/POST /collectivite/nouveau, /collectivite/{id}
│   │   ├── projets.py           — GET/POST /projet/nouveau, /projet/{id}
│   │   ├── sous_objets.py       — GET/POST /projet/{id}/{cas-usage|partenaire|programme|document|contact}/nouveau
│   │   └── restitution.py       — GET /restitution + GET /api/restitution/donnees (401 sans session)
│   ├── repositories/
│   │   ├── __init__.py
│   │   ├── grist_session.py     — requests.Session partagée : timeout global, retries bornés (urllib3
│   │   │                          Retry), pool_maxsize ≥ 8 (lectures parallèles), erreurs reformulées
│   │   │                          sans doc ID ; la clé API ne sort jamais d'ici
│   │   ├── cache.py             — cache TTL 5 min (tables de réf + choix widgetOptions) + invalidation par table
│   │   ├── types.py             — TypedDicts des records des 12 tables BDD_*
│   │   ├── base.py              — CRUD générique sur GristApi : helpers ref_ids/to_reflist/extraction
│   │   │                          tolérante, batching PATCH homogène + repli unitaire, status vérifiés
│   │   ├── utilisateur_repository.py   — recherche par email (insensible casse), création « En attente »,
│   │   │                                 maj droits, normalisation droits anglais→français à la lecture
│   │   ├── collectivite_repository.py  — CRUD + projets liés (RefList directe + recherche inverse)
│   │   ├── projet_repository.py        — CRUD projets + liaison collectivité porteuse
│   │   ├── reference_repository.py     — lectures cachées : connectivités, départements, contrats, solutions
│   │   ├── cas_usage_repository.py     — cas d'usage groupés par thème, liaison multi-projets
│   │   ├── partenaire_repository.py    — partenaires (+ add_to_reflist Projets)
│   │   ├── programme_repository.py     — programmes (+ add_to_reflist projet_s_)
│   │   ├── document_repository.py      — documents (Ref simple projet)
│   │   └── contact_repository.py       — contacts (projet_s_ = Text → nom du projet, comportement v1)
│   └── services/
│       ├── __init__.py
│       ├── types.py             — modèles Pydantic des formulaires (Login, Inscription, Collectivite,
│       │                          Projet, CasUsage, Partenaire, Programme, Document, Contact, AdminUpdate),
│       │                          HttpUrl sur tous les champs URL (anti `javascript:`), constante DROITS
│       │                          (5 valeurs françaises ; « Extention » commentée : valeur de données)
│       ├── auth_service.py      — mapping email→rôle (BDD_Utilisateurs), workflow En attente/élévation,
│       │                          réponses neutres anti-énumération ; conçu pour brancher l'OIDC ensuite
│       ├── magic_link_service.py — tokens signés itsdangerous (salt dédié) : TTL 15 min, usage unique
│       │                          réel (magasin mémoire des jetons consommés + boot-id : un redémarrage
│       │                          invalide les jetons antérieurs), URL bâtie sur APP_PUBLIC_URL uniquement
│       ├── admin_service.py     — tri utilisateurs, validation/refus, garde-fou anti-auto-rétrogradation
│       ├── collectivite_service.py — règles création/édition (formules dep→num_dep/reg jamais écrites)
│       ├── projet_service.py    — création/édition projet + agrégation des sous-formulaires
│       ├── restitution_service.py — agrège carte/donuts/pills/tableau (to_thread + gather, index mémoire),
│       │                          payload JSON identique v1, cache TTL 5 min invalidé sur écriture
│       ├── geo_service.py       — port de geo_resolver v1 (mêmes règles), départements injectés depuis Grist
│       ├── geocode_client.py    — api-adresse.data.gouv.fr : timeout 10 s, validation départementale, cache
│       └── notification_service.py — SMTP : magic links + notification admin (dormant si non configuré)
│
├── templates/                   — les 15 templates v1 repris de reference_ui/ (base, login, inscription,
│                                  acces_refuse, menu, admin, accueil, collectivite, projet_form, cas_usage,
│                                  partenaire, programme, document, contact, restitution) — UX inchangée —
│                                  + confirmation_lien.html (page de confirmation magic link, style v1)
│                                  + mentions_legales.html (RGPD — contenu à fournir par Victor)
├── static/
│   ├── style.css                — CSS v1 inchangé
│   ├── logo.jpg                 — logo FNCCR v1
│   ├── js/restitution.js        — JS de la page restitution externalisé (comportement identique)
│   ├── js/app.js                — petits scripts inline de base/accueil/cas_usage externalisés (CSP)
│   └── vendor/leaflet/          — Leaflet 1.9.4 auto-hébergé (js + css + images)
│
├── scripts/
│   ├── check_grist_schema.py    — compare (lecture seule) le schéma Grist réel à SCHEMA_GRIST.md ;
│   │                              aussi appelé au démarrage de l'app (log CRITICAL si divergence)
│   ├── export_grist.py          — export daté du document Grist (.grist + xlsx via l'API) — à lancer
│   │                              avant go-live et avant tout script one-shot (sauvegarde D1)
│   └── nettoyage_droits.py      — [optionnel, sur accord Victor] migration droits anglais→français
│                                  via l'API ; dry-run par défaut, exécution sur double confirmation
│
└── tests/                       — voir 04_TESTS.md
    ├── conftest.py              — fixtures + cache_clear() des fabriques @lru_cache (isolation)
    ├── unit/   (7 fichiers : repositories, cache, auth, magic link, geo, restitution, formulaires)
    └── api/    (9 fichiers : auth, accès, IDOR (GET+POST), CSRF, headers, rate limit, admin,
                 CRUD, API restitution)
```

≈ 70 fichiers. Aucune fixture ne contiendra de données réelles du kit (jeux synthétiques uniquement).
