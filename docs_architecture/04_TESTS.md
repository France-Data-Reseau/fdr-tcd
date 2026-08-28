# Stratégie de tests

> Révisé suite aux revues du 2026-06-12 (`revues/`) : cas GET dans les tests IDOR (B2),
> tests rate-limit/proxy (S3), SMTP en panne (S4), jetons magic link (S1), headers (R3).

Objectif (BRIEF §3.1) : pas 100 % de couverture, mais **les chemins critiques** —
services, repositories (Grist mocké), smoke tests des routes, et tests de sécurité.

## Outillage

- **pytest + pytest-asyncio** (config dans `pyproject.toml`, comme la référence).
- **pygrister mocké** dans les tests de repositories/services (pattern des
  `test_*_repository.py` du repo de référence : mock de `GristApi`, vérification des
  appels et des retours `(status, data)`).
- `TestClient` FastAPI avec sessions forgées par rôle pour les tests de routes.
- **Isolation** : les fabriques `@lru_cache` de `dependencies.py` sont des singletons →
  `cache_clear()` systématique dans les fixtures (`conftest.py`), sinon les tests fuient
  l'un dans l'autre.
- Exécution : `uv run pytest` ; lint `uv run ruff check` ; typage `uv run pyright`
  (pre-commit rejoue les deux derniers). **Garde-fou de livraison (R2)** : la séquence
  complète est exigée avant tout build d'image de déploiement (cf. `05` étape 2) ;
  un workflow CI (GitHub Actions : ruff + pyright + pytest) la formalise dès que le
  dépôt est hébergé.

## tests/unit/ — logique pure et accès données

| Fichier | Ce qui est testé |
|---|---|
| `test_repositories.py` | CRUD générique sur GristApi mocké : status vérifiés, batching PATCH homogène + repli unitaire (piège n°2), helpers `ref_ids`/`to_reflist`/extraction tolérante (pièges n°3 et 6), **invalidation du cache déclenchée par les méthodes d'écriture de `base.py`** (pas par les services) |
| `test_cache.py` | TTL 5 min, invalidation ciblée par table après écriture |
| `test_auth_service.py` | Mapping email→rôle, workflow En attente/élévation, neutralité des réponses (login ET inscription), normalisation droits anglais→français |
| `test_magic_link_service.py` | Expiration (15 min), **usage unique : jeton rejoué → rejeté**, **jeton d'un boot précédent → rejeté**, jeton falsifié → rejeté, salt distinct des sessions |
| `test_geo_service.py` | Cas réels v1 : acronymes (SDE 22, SIPPEREC…), entités régionales, validation départementale, overrides |
| `test_restitution_service.py` | Agrégats donuts/stats/filtres + structure JSON v1 sur jeu de données **synthétique** ; absence des champs sensibles (pas d'emails/téléphones) |
| `test_form_types.py` | Validation Pydantic : rejets attendus (email invalide, IDs non entiers, longueurs, **`javascript:` refusé sur les champs URL** — `HttpUrl`) |

## tests/api/ — routes et sécurité

| Fichier | Ce qui est testé |
|---|---|
| `test_auth_routes.py` | Login (envoi du lien)/inscription/logout : 303, flash, neutralité ; `/auth/verifier` : **GET sans effet de bord, consommation par POST uniquement** ; régénération de session à la connexion ; **SMTP en panne → message neutre, pas de 500** |
| `test_acces.py` | **Matrice rôles × routes** : sans session → 303 login ; En attente → acces-refuse ; Visiteur → pas d'écriture ; API → 401 |
| `test_idor.py` | Éditeur hors périmètre → **404 en GET ET en POST** sur collectivité, projet et chaque sous-objet d'une autre collectivité (IDs forgés) ; Administrateur exempté |
| `test_csrf.py` | Tout POST sans token ou token invalide → 403 |
| `test_headers.py` | Présence et valeur des headers de sécurité émis par l'app (CSP, X-Content-Type-Options, Referrer-Policy) ; `Cache-Control: private` sur l'API restitution |
| `test_rate_limit.py` | Key function fondée sur l'IP transmise : deux `X-Forwarded-For` différents = compteurs distincts (S3) ; limite par email ciblé sur l'envoi de magic link |
| `test_admin_routes.py` | Validation des comptes, changement de droits, garde-fou anti-auto-rétrogradation ; **prise d'effet d'une rétrogradation ≤ 5 min** (rôle re-résolu à chaque requête, S5) |
| `test_collectivite_projet_routes.py` | Smoke CRUD complet collectivité + projet + sous-formulaires (Grist mocké) |
| `test_restitution_api.py` | Structure JSON conforme v1, 401 sans session, absence des champs sensibles dans le payload |

## Règles

- **Aucune donnée réelle du kit dans les fixtures** (emails de contacts réels notamment) —
  jeux de données synthétiques uniquement.
- Les idiomes Grist (`(status, data)`, `['L', id…]`) ne doivent **jamais** apparaître dans
  les tests de services : s'ils y apparaissent, l'abstraction repository est percée
  (règle inscrite dans AGENTS.md).
- Chaque étape de développement se termine par : app qui démarre + pytest vert + ruff propre.
- e2e Playwright (comme le repo de référence) : hors périmètre initial, ajoutable ensuite
  sur le même modèle (`tests/e2e/`) si Victor le souhaite.
