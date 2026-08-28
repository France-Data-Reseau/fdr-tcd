# 12. Mise en production de la version SSO

> Runbook pour faire de la nouvelle version (SSO uniquement) **la production**,
> en remplacement de l'ancien `fdr2`. Public : technicien (dev FDR / Claude).
> Suppose acquis : le nettoyage des colonnes Grist (déjà fait le 2026-08-27) et
> l'environnement de test validé (`app-dev.example.org`).
> Voir aussi : `05_DEPLOIEMENT.md` (build offline), `10_CADRAGE_BASCULE_SSO.md`.

---

## 1. Où on part / où on va

- **Aujourd'hui** : la nouvelle version tourne en **test** sur `app-dev.example.org`,
  branchée sur le **Grist de prod** (déjà renommé) et un **Keycloak de test** local.
  L'ancien `fdr2` (code pré-SSO) tourne encore mais est **cassé** (colonnes
  renommées) — il sera remplacé.
- **Cible prod** : la nouvelle version sur le domaine de prod (`app.example.org`
  ou un domaine dédié), branchée sur l'**IdP de France Data Réseau**
  (`id.francedatareseau.fr`) au lieu du Keycloak de test.

**Le seul vrai changement test → prod = l'IdP** (config `.env`, aucun changement
de code, l'OIDC est générique).

---

## 2. Prérequis

- [ ] Accès SSH au VPS (`ssh vps`), reverse proxy **Caddy** (`~/stack`).
- [ ] Colonnes Grist renommées (fait) + **sauvegarde Grist** fraîche.
- [ ] **Client OIDC obtenu auprès de France Data Réseau** (voir §3).
- [ ] Comptes des utilisateurs créés côté IdP FDR + lignes `BDD_Utilisateurs`
      correspondantes (voir §6).

---

## 3. Obtenir le client OIDC de France Data Réseau *(action externe, non technique)*

Demander à l'opérateur de `id.francedatareseau.fr` :
- l'**URL de l'issuer** OIDC (ex. `https://id.francedatareseau.fr/realms/<realm>`) ;
- l'**enregistrement d'un client** pour l'app, avec la **redirect URI** exacte
  `https://<domaine-prod>/auth/callback` ;
- le **`client_id`** (et le `client_secret` si client confidentiel ; inutile si
  client public avec PKCE).

Tant que ces valeurs ne sont pas là, la prod ne peut pas basculer en SSO — mais
l'app est déjà prête (le connecteur est le même que pour le Keycloak de test).

---

## 4. Build hors-ligne (rappel)

Le VPS ne joint pas PyPI (IPv6 cassé) → build **offline** depuis des wheels Linux
pré-téléchargées :
1. Générer les wheels en local :
   `python -m pip download -r requirements.txt -d wheels --only-binary=:all: --python-version 311 --platform manylinux_2_28_x86_64 --platform manylinux_2_17_x86_64 --platform manylinux2014_x86_64 --platform any`
2. Transférer code + wheels sur le VPS, `Dockerfile` en mode offline
   (`pip install --no-index --find-links=wheels/`).

*(La dépendance `fastapi-oidc` s'ajoute aux wheels de l'ancienne version ;
`authlib` n'est plus nécessaire.)*

---

## 5. Configuration `.env` de prod

```env
ENVIRONMENT=production
SECRET_KEY=<nouvelle clé forte, jamais celle du test>
APP_PUBLIC_URL=https://<domaine-prod>
GRIST_API_KEY=<clé/compte de service Grist>
GRIST_DOC_ID=<GRIST_DOC_ID>     # doc de prod (renommé)
GRIST_SERVER_URL=https://grist.francedatareseau.fr
OIDC_ISSUER=https://id.francedatareseau.fr/realms/<realm>
OIDC_CLIENT_ID=<client_id FDR>
OIDC_CLIENT_SECRET=<si client confidentiel, sinon vide>
```
⚠️ `ENVIRONMENT=production` durcit la config (exige `SECRET_KEY`, cookies Secure,
HSTS). `chmod 600 .env`.

---

## 6. Provisionner les administrateurs et éditeurs

Modèle retenu (cf. doc 10) : **identité côté IdP FDR, droits côté Grist**. Pour
chaque personne, **deux créations avec le même email** :
1. un **compte dans l'IdP FDR** (fait par FDR) ;
2. une **ligne `BDD_Utilisateurs`** (email + nom + `droits` + collectivité).

Admins à provisionner : Loïc Hay, Pierre-Alban Bonin, Victor Welschinger
(emails fournis séparément). Sans ligne Grist, un email valide côté IdP se verra
refuser l'accès (liste fermée).

---

## 7. Déploiement & bascule

1. **Sauvegarde Grist** (`scripts/export_grist.py`).
2. Transférer le code + wheels (nouveau dossier, ex `~/stack/app_fdr_v2` mis à
   jour, ou dossier dédié).
3. `.env` de prod en place (§5).
4. `docker compose build <service>` puis `docker compose up -d <service>`.
5. **Router le domaine de prod** vers le nouveau conteneur dans le `Caddyfile`
   (sauvegarde du Caddyfile avant), puis `docker compose exec caddy caddy reload`.
6. Vérifier `GET /health`, puis un **login SSO réel** (un admin), puis la carto.

---

## 8. Vérifications post-bascule

- [ ] `https://<domaine-prod>/health` → `ok`.
- [ ] Login SSO d'un admin → session avec le bon droit.
- [ ] Cartographie : données présentes (collectivités, projets, cas d'usage).
- [ ] Une écriture (édition d'une collectivité) → « mise à jour avec succès ».

---

## 9. Rollback

- **Grist** : restaurer depuis la sauvegarde (`sauvegardes_grist_*`) si les
  données sont touchées.
- **App** : Caddy re-router vers l'ancien conteneur (backups `Caddyfile.bak-*`
  et `docker-compose.yml.bak-*` conservés à chaque modif) et `caddy reload`.
- Les renommages de colonnes se **ré-inversent** par le même script
  (`RenameColumn`) si nécessaire.

---

## 10. Points de vigilance

- **Mono-worker** : ne jamais ajouter `--workers` (cache mémoire, rate limiting,
  sessions reposent sur 1 process).
- **La V1 (`app-v1.example.org`) est abandonnée** ; ne pas la remettre en service sur
  le doc renommé (elle lit les anciens noms).
- **Ménage avant tout dépôt public** : retirer les dossiers de documentation
  interne, ne jamais committer de `.env` ni de données personnelles.
- Le **Keycloak de test** (`keycloak-dev.example.org`) et le sous-domaine
  `app-dev` peuvent être **retirés** une fois la prod sur l'IdP FDR validée
  (supprimer les 2 services du compose + les 2 blocs Caddy).
