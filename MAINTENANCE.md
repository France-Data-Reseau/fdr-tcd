# MAINTENANCE — à lire avant de modifier ce projet

> Document destiné aux développeurs qui reprendront ce projet, avec ou sans
> assistance IA. Les règles ci-dessous ne sont pas des préférences de style :
> les enfreindre casse des mécanismes de sécurité ou des données de manière
> silencieuse. Complément : `AGENTS.md` (invariants) et `docs_architecture/`.

## A. Le « secret de fabrication » : MONO-WORKER

L'application tourne avec **UN SEUL processus uvicorn** (pas de `--workers N`,
pas de réplique du conteneur). Trois mécanismes critiques vivent **dans la
mémoire de ce processus** :

1. le **cache des tables Grist** (`app/repositories/cache.py`, TTL 5 min,
   invalidé par les écritures) ;
2. le **magasin des jetons magic link consommés** + le boot-id
   (`app/services/magic_link_service.py`) — c'est ce qui garantit l'usage
   unique des liens de connexion ;
3. les **compteurs de rate limiting** (slowapi + limite par email).

**Si vous passez à plusieurs workers ou répliques**, ces trois mécanismes
casseront de manière asynchrone et aléatoire : liens de connexion rejouables
(faille de sécurité), données périmées servies après une écriture, limites de
débit inopérantes. Le passage à N workers exige d'introduire un magasin
partagé (Redis) pour les trois — c'est un chantier, pas un réglage.

L'absence de Redis est un **choix délibéré** : à l'échelle de l'application
(~260 collectivités, ~10 utilisateurs), un process unique suffit largement,
et chaque service en moins sur le VPS est un service qu'on n'exploite pas.

Verrous en place : `CMD` du Dockerfile sans `--workers`, note dans AGENTS.md,
`mem_limit` dans le compose.

## B. Migration / changement de domaine

Si l'application quitte `app.example.org` :

1. **`.env` à modifier** (sur le VPS, `chmod 600`) :
   - `APP_PUBLIC_URL` — **critique** : les liens des emails (magic links,
     notifications admin) sont construits EXCLUSIVEMENT depuis cette
     variable, jamais depuis le header Host (anti-empoisonnement). Si elle
     est fausse, plus personne ne peut se connecter.
   - `OIDC_*` si le SSO est actif : la redirect URI déclarée chez l'IdP doit
     suivre (`https://<nouveau-domaine>/auth/callback`).
   - `SECRET_KEY` reste inchangée (la changer déconnecte tout le monde et
     invalide les liens en circulation — acceptable mais à savoir).
2. **DNS** : enregistrement A vers l'IP du serveur AVANT le premier
   démarrage (certificat Let's Encrypt du premier coup).
3. **Caddyfile** : dupliquer le bloc du domaine, `caddy reload`.
4. **Livraison** : `scripts/deploiement.ps1` fait tout (vérification, wheels
   Linux téléchargées en local, transfert du code + wheels, **build SUR le
   VPS hors-ligne** — son résolveur IPv6 rend PyPI inaccessible, il ne doit
   jamais le contacter — puis contrôles v2 ET v1). Pas besoin de Docker sur
   le poste. Détail complet : `docs_architecture/05_DEPLOIEMENT.md`.

## C. Lexique des dettes techniques ASSUMÉES (ne pas « corriger »)

| Dette | Explication | Si vous y touchez |
|---|---|---|
| **« Extention »** (sic) | Valeur de droit présente telle quelle dans les données Grist (`BDD_Utilisateurs.Droits`). L'orthographe est volontairement conservée — constante `DROIT_EXTENTION` dans `app/repositories/types.py`. | Corriger l'orthographe dans le code SANS migrer les données casse silencieusement les contrôles d'accès des utilisateurs concernés. |
| **Contacts liés par NOM de projet** | `BDD_Contacts.projet_s_` est un champ **Text** contenant le nom du projet (héritage v1, imports historiques). Pas une référence. | Renommer un projet orpheline ses contacts. Une migration vers une vraie RefList est possible mais exige l'accord du propriétaire du document Grist (modification de schéma). |
| **Droits anglais → français** | Le schéma Grist accepte encore `Administrator`, `Editor`, `Viewer`, `Pending` (héritage). L'app les **traduit à la lecture** (`utilisateur_repository._normalise`) et n'écrit QUE les valeurs françaises. | Supprimer la normalisation rend invisibles les utilisateurs porteurs d'une valeur anglaise. Nettoyage one-shot possible via l'API (jamais l'interface Grist). |
| **Champs formule jamais écrits** | `num_dep`, `reg`, `Theme_s_`, `region`, `partenaire_s_`, `cas_d_usage`, `prenom_nom`… sont calculés par Grist. Ils sont signalés dans `repositories/types.py`. | Les envoyer dans un PATCH provoque une erreur Grist (ou pire, selon les versions). |
| **Hash de mot de passe dans Grist** | La colonne `BDD_Utilisateurs.password_hash` stocke un hash **argon2id** (jamais le mot de passe en clair). Choix « pour le moment » de Victor : les hash sont donc visibles par les admins de l'instance Grist FDR. Voir `docs_architecture/02_AUTHENTIFICATION.md` et `07_STRATEGIE_AUTH.md`. | Le hash ne doit jamais sortir de `password_service.py` (logs/API/templates exclus). Pour migrer le stockage hors Grist : voir l'option B du `07`. |
| **CSP : `unsafe-inline` pour les STYLES uniquement** | Les templates v1 (conservés iso-UX) utilisent massivement des attributs `style=""`. Les **scripts**, eux, sont 100 % externalisés (`static/js/`) et la CSP n'autorise AUCUN script inline. | Ajouter un `<script>` inline dans un template ne fonctionnera pas (CSP). C'est voulu : créez un fichier sous `static/js/`. |

## D. Évolutions du schéma Grist

**Règle n°1 : ne jamais modifier le schéma via l'INTERFACE Grist** (changer le
type ou la cible d'une colonne par l'interface EFFACE les données ; via
l'API, elles sont préservées). Toute migration = script API + export préalable.

**Vérifier la conformité** à tout moment :
```bash
uv run python -m scripts.check_grist_schema   # exit 1 si divergence
```
Le même contrôle tourne au démarrage de l'app (log CRITICAL si une table ou
colonne attendue a disparu). Le schéma attendu vit dans
`scripts/check_grist_schema.py` (`SCHEMA_ATTENDU`).

**Marche à suivre pour AJOUTER un champ** (ex. un champ sur la fiche projet) :
1. Ajouter la colonne dans Grist (avec l'accord du propriétaire du document).
2. `app/repositories/types.py` : l'ajouter au TypedDict de la table
   (+ `SCHEMA_ATTENDU` du script si l'app en dépend).
3. `app/services/types.py` : l'ajouter au modèle Pydantic du formulaire
   (types, longueur max, `HttpUrl` si c'est une URL).
4. Le service concerné (`app/services/*_service.py`) : l'ajouter à la liste
   blanche `_fields()` — rien n'est écrit vers Grist hors de ces listes.
5. La route (`app/api/*.py`) : ajouter le paramètre `Form(...)`.
6. Le template : ajouter le champ HTML.
7. Les tests : cas nominal + rejet de valeur invalide.

**Sauvegarde avant toute opération d'écriture de masse.** Attention : le
`.env` LOCAL contient des clés Grist factices (les tests mockent tout) —
l'export doit tourner là où vivent les vraies clés, c'est-à-dire **dans le
conteneur de production** :
```bash
ssh vps "cd ~/stack && docker compose exec fdr2 python -m scripts.export_grist"
ssh vps "cd ~/stack && docker cp fdr2:/app/exports_grist ./sauvegardes_grist_$(date +%Y%m%d)"
```
Puis redescendre une copie HORS du VPS (scp vers le poste). C'est ainsi qu'a
été faite la sauvegarde du 2026-06-12 (`~/stack/sauvegardes_grist_20260612`).
Le **seul document Grist est celui de la production, partagé avec la v1** :
il n'existe aucun document de test — aucune écriture « pour essayer ».

## E. Vérification avant toute livraison

```bash
uv run ruff check app tests scripts && uv run pyright && uv run pytest
```
(Si `uv` n'est pas dans le PATH — cas du poste de Victor — préfixer :
`python -m uv run …`.) Rien ne part en production sans cette séquence au
vert ; le déploiement passe par `scripts/deploiement.ps1`, qui la rejoue
puis vérifie en fin de course que la BONNE version répond (`/health` = SHA)
et que **la v1 répond toujours**.
