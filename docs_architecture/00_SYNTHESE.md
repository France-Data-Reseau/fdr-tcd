# Proposition d'architecture V2 — Synthèse pour revue

> Statut : **en attente de validation explicite de Victor** — aucun code écrit.
> Dernière mise à jour : 2026-06-12 — **intègre les deux revues du dossier `revues/`**
> (retours_gemini.md, revue-claude.md) : les 2 constats bloquants et l'ensemble des points
> importants/recommandés ont été traités dans les documents.

## Documents du dossier

| Fichier | Contenu |
|---|---|
| `01_ARCHITECTURE.md` | Couches, règles d'étanchéité, choix techniques justifiés, **liste exhaustive des fichiers** |
| `02_AUTHENTIFICATION.md` | SSO OIDC (client public PKCE), mapping des rôles et sessions |
| `03_SECURITE.md` | Plan anti-exfiltration (lectures comprises), checklist 17 points, droits, RGPD |
| `04_TESTS.md` | Stratégie de tests, dont sécurité (IDOR GET+POST, rate limit, jetons) |
| `05_DEPLOIEMENT.md` | Livraison par image Docker, protection de la v1 (ressources, logs) |

## Réponses aux constats majeurs des revues

| Constat | Réponse |
|---|---|
| **B1** — chaîne de livraison `wheels/` incohérente (build VPS impossible) | **Livraison par image** : build + tests en local, `docker save` → `scp` → `docker load`, compose en `image:`. Le VPS ne contacte plus jamais PyPI (`05`) |
| **B2** — anti-IDOR limité aux écritures → annuaire des contacts siphonnable par GET | `require_ownership` étendu aux **GET paramétrés de complétion** ; hors périmètre → **404** ; cas GET ajoutés aux tests (`01`, `03`, `04`) |
| **S1/S2** — flux d'auth fragile | Auth unifiée sur OIDC Authorization Code + PKCE (`S256`) ; `state`/`nonce`/`code_verifier` en session ; URL de callback bâtie sur `APP_PUBLIC_URL` (`02`) |
| **S3** — rate limiting aveugle derrière Caddy | uvicorn `--proxy-headers --forwarded-allow-ips` + key function sur l'IP transmise, testé avec `X-Forwarded-For` (`01`, `03`, `04`) |
| **S4** — erreurs d'auth non maîtrisées | Démarrage SSO robuste : indisponibilité IdP/metadata => retour login avec message sobre, sans 500 (`02`) |
| **S5–S8** — sessions, headers, CSP, URLs | Session = identité seule (rôle re-résolu à chaque requête, effet admin ≤ 5 min) ; un émetteur par header (CSP=app, HSTS=Caddy) ; CSP fondée sur l'inventaire réel (5 scripts inline externalisés, tuiles OSM) ; `HttpUrl` partout (`03`) |
| **D1–D6** — sauvegarde, clé API, healthcheck, ressources, réseau, mono-worker | `scripts/export_grist.py` avant go-live et tout one-shot ; question compte de service posée ; `/health` sans I/O externe ; `mem_limit`/`cpus`/rotation des logs (protège la v1) ; `networks:` à aligner sur le compose réel ; mono-worker = invariant écrit (`01`, `03`, `05`) |
| **R1–R6, N1–N6** | SHA dans `/health`, garde-fou « verify avant build », tests complémentaires, RGPD (mentions légales, rétention En attente), dette « contacts liés par nom » actée ci-dessous, « Extention » protégée par commentaire, pool_maxsize, reload Caddy explicite, salts distincts, `Cache-Control: private` |

## Décisions actées avec Victor

1. **Architecture en couches à étanchéité stricte** (repositories / services / api) — priorité n°1.
2. **pygrister** (0.9.x) pour l'accès Grist ; risque threadpool sous forte charge accepté et
   documenté, issue de secours httpx derrière les mêmes Protocols.
3. **Grist = unique source de données** (12 tables `BDD_*`), schéma jamais modifié sans accord.
4. **Auth : SSO OIDC uniquement** (IdP derrière grist.francedatareseau.fr).
5. **Droits exclusivement en français** ; valeurs anglaises normalisées à la lecture.
6. **UX/UI strictement identique à la v1** ; assainissements invisibles : JS externalisé
   (CSP), Leaflet auto-hébergé.

## Dettes et limites assumées (énoncées, pas masquées)

- `BDD_Contacts.projet_s_` est un champ **Text** (nom du projet) : renommer un projet
  orphelinise ses contacts. Comportement v1 conservé (iso-fonctionnel) ; migration vers une
  vraie référence possible plus tard, sur accord schéma (R5).
- **Mono-worker + cache mémoire** : passage à N workers impossible sans magasin partagé
  (Redis) — verrouillé et documenté (D6).
- **Grist sans transactions** : écritures multi-tables ordonnancées pour minimiser les états
  incohérents ; pas de rollback possible (revue Claude).
- Couplage repository↔Grist intime (RefList, batching) : c'est le rôle de cette couche ;
  les services n'en voient rien (frontière testée).

## Règles absolues (rappel du contrat)

- Ne jamais toucher à l'app v1, au service Docker `fdr`, ni à `fdr.revorun.eu`.
- Ne jamais modifier le schéma Grist sans accord explicite.
- Aucun secret en dur — tout en `.env` (`.env.example` fourni).
- Validation de Victor avant le code ; ensuite étapes courtes et testables.

## Points ouverts pour Victor

1. **Go / no-go** sur cette architecture (déclenche l'étape 1 : socle projet + repositories + tests).
2. **Dépendance OIDC externe** : stratégie de secours en cas d'indisponibilité IdP
   (maintenance IdP, coupure réseau) — quel runbook ?
3. **Sauvegarde Grist** : qui déclenche l'export avant le go-live, où le stocker (hors VPS) ?
4. **Clé API Grist** : celle de la v1 est-elle un compte de service dédié limité à ce
   document ? Sinon, peut-on en créer un ?
5. **Nettoyage one-shot** des droits anglais dans Grist : oui/non (script dry-run fourni).
6. **Confirmation périmètre** : sous-objet « document » = lien uniquement, aucun upload de
   fichier (comme en v1).
7. **Contenu des mentions légales / politique de confidentialité** (RGPD) — texte à fournir,
   la page est prévue.
8. Demander à France Data Réseau l'enregistrement OIDC (non bloquant pour démarrer).
