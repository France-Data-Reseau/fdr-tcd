# Migration de l'app Formulaire FNCCR vers un nouveau serveur

> **Domaine cible : `tcd.francedatareseau.fr`**
>
> Guide destiné à la personne qui déploiera l'application sur un nouveau serveur.
> Aucune connaissance préalable du projet n'est requise. Compter ~30 minutes.

---

## 1. Ce qu'il faut comprendre avant de commencer

L'application est un **formulaire web de saisie + restitution** (Python / FastAPI),
server-rendered. Point essentiel :

> ### 🟢 L'app est SANS ÉTAT — il n'y a AUCUNE donnée à migrer.
> Toutes les données (collectivités, projets, utilisateurs, droits…) vivent dans
> un **Grist externe** : `https://grist.francedatareseau.fr`. L'app ne fait que
> lire/écrire dans ce Grist via son API. Il n'y a **pas de base de données locale**,
> pas de volume de données applicatives à sauvegarder.

**Migrer = redéployer le même code, avec le même `.env` (accès Grist), derrière le
nouveau domaine.** C'est tout.

Les seules dépendances externes :
1. **L'instance Grist** (`grist.francedatareseau.fr`) — données + comptes utilisateurs.
2. **Un accès réseau sortant HTTPS** depuis le serveur vers ce Grist (port 443).

> 🔒 **Cette livraison ne contient AUCUN secret.** Le fichier `.env` (clé d'API
> Grist, clé de session…) n'est pas fourni : tu le crées à partir de
> `.env.example` (section 7). Les valeurs `GRIST_API_KEY` et `GRIST_DOC_ID` te
> seront communiquées séparément par la FNCCR / Victor Welschinger.

---

## 2. Contenu de ce dossier (`Migration_1/`)

| Fichier | Rôle |
|---|---|
| `MIGRATION.md` | Ce guide. |
| `docker-compose.yml` | Stack autonome : l'app (`tcd`) + un reverse proxy `caddy` (TLS auto). |
| `Caddyfile` | Route HTTPS `tcd.francedatareseau.fr` → app. |
| `.env.example` | Modèle de configuration à copier en `.env` et remplir. |

> ⚠️ Ce dossier **s'appuie sur le code de l'application**, qui se trouve dans le
> dossier **parent** (`app_form_fnccr/`). Le `docker-compose.yml` utilise
> `build.context: ..`. Il faut donc **copier tout le dossier `app_form_fnccr/`**
> (qui contient `Migration_1/`) sur le nouveau serveur — pas seulement `Migration_1/`.

---

## 3. Prérequis

- **Docker** + **Docker Compose v2** installés sur le serveur (`docker compose version`).
- **Ports 80 et 443** ouverts/entrants sur le serveur (pour Caddy + Let's Encrypt).
- **Accès réseau sortant HTTPS** vers `grist.francedatareseau.fr`.
- Les **secrets Grist** de l'app actuelle :
  - `GRIST_API_KEY` (clé API Grist, avec droits lecture + écriture sur le document)
  - `GRIST_DOC_ID` (ID du document Grist)
  - → on les retrouve dans le `.env` du serveur actuel
    (`~/stack/app_form_fnccr/.env` sur le VPS revorun.eu), ou dans le gestionnaire
    de mots de passe.

---

## 4. DNS — pointer le domaine vers le nouveau serveur

Créer un enregistrement **A** (et idéalement **AAAA** si IPv6) :

```
tcd.francedatareseau.fr.   A   <IP_DU_NOUVEAU_SERVEUR>
```

Vérifier la propagation :
```bash
dig tcd.francedatareseau.fr +short      # doit retourner l'IP du nouveau serveur
```

> Le certificat TLS sera obtenu **automatiquement** par Caddy (Let's Encrypt) à la
> première requête, une fois le DNS résolu. Le DNS doit donc pointer **avant** de
> lancer le stack (sinon l'émission du certificat échoue et Caddy réessaiera).

---

## 5. Déploiement (Option A — stack autonome avec Caddy fourni)

C'est l'option recommandée si le serveur n'a pas déjà de reverse proxy.

```bash
# 1. Copier tout le dossier de l'app sur le serveur (exemples) :
#    - via git :   git clone <repo> app_form_fnccr
#    - ou via scp/rsync du dossier app_form_fnccr/ complet
#    Puis :
cd app_form_fnccr/Migration_1

# 2. Créer le .env à partir du modèle et le remplir (voir section 7)
cp .env.example .env
nano .env                      # renseigner GRIST_API_KEY, GRIST_DOC_ID, SECRET_KEY, LE_EMAIL

# 3. Construire et démarrer
docker compose up -d --build

# 4. Vérifier le démarrage de l'app
docker compose logs tcd --tail 50      # doit afficher : "Connexion Grist OK"

# 5. Vérifier le TLS / l'accès public (après propagation DNS)
curl -I https://tcd.francedatareseau.fr     # 200 ou 303 (redirection vers /login) attendu
```

Exploitation courante :
```bash
docker compose ps                      # état des conteneurs
docker compose logs tcd -f             # logs de l'app en direct
docker compose logs caddy --tail 30    # logs du proxy (utile si souci de certificat)
docker compose restart tcd             # redémarrer l'app
docker compose up -d --build tcd       # rebuild après mise à jour du code
docker compose down                    # arrêter (NE PAS ajouter -v, inutile ici)
```

---

## 6. Déploiement (Option B — serveur avec reverse proxy existant)

Si le serveur a déjà Caddy / nginx / Traefik qui gère le TLS, on ne garde que l'app :

1. Dans `docker-compose.yml`, **supprimer le service `caddy`** (et la section
   `networks` peut rester). Le service `tcd` n'a pas de `ports:` ; pour que le proxy
   existant l'atteigne, soit le mettre sur le réseau du proxy, soit ajouter
   temporairement `ports: ["127.0.0.1:8000:8000"]` et proxifier vers `127.0.0.1:8000`.
2. Démarrer : `docker compose up -d --build tcd`.
3. Ajouter une route dans le proxy existant vers le conteneur `tcd` sur le port **8000**.
   Exemple Caddy :
   ```caddyfile
   tcd.francedatareseau.fr {
       encode gzip
       reverse_proxy tcd:8000
   }
   ```
   Exemple nginx : `proxy_pass http://127.0.0.1:8000;` (si port publié en local).

> Dans tous les cas : **le port 8000 de l'app ne doit jamais être exposé
> publiquement** — uniquement accessible par le reverse proxy.

---

## 7. Variables d'environnement (`.env`)

| Variable | Obligatoire | Rôle / valeur |
|---|---|---|
| `GRIST_API_KEY` | ✅ | Clé API Grist (mêmes données qu'aujourd'hui → réutiliser la valeur existante). **Secret.** |
| `GRIST_DOC_ID` | ✅ | ID du document Grist (réutiliser la valeur existante). |
| `SECRET_KEY` | ✅ | Clé de signature des cookies. Générer une **nouvelle** valeur fixe : `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Peut différer de l'ancien serveur (ça ne fait qu'invalider les anciennes sessions, sans importance sur un nouveau serveur). |
| `ENVIRONMENT` | ✅ | `production` (cookies Secure + HSTS). |
| `LE_EMAIL` | ✅ (option A) | Email pour Let's Encrypt (certificat TLS). |
| `APP_PUBLIC_URL` | ➖ | `https://tcd.francedatareseau.fr` (lien dans les emails). |
| `SMTP_*`, `ADMIN_NOTIFY_EMAILS` | ➖ | Notification email des nouvelles inscriptions. **Dormant** si non renseigné (voir `.env.example`). |

> `GRIST_BASE_URL` est codé en dur dans `grist_client.py`
> (`https://grist.francedatareseau.fr`). À ne changer **que** si l'on migre aussi
> vers une autre instance Grist (ce n'est pas le cas ici).

---

## 8. Prérequis côté Grist (ne rien casser)

L'app a besoin que le document Grist (`GRIST_DOC_ID`) contienne ces 9 tables :

| Clé interne | Table Grist |
|---|---|
| collectivites | `BDD_Collectivites` |
| projets | `BDD_Projets` |
| contacts | `BDD_Contacts` |
| cas_d_usage | `BDD_CasUsages` |
| partenaires | `BDD_Partenaires` |
| programmes | `BDD_Programmes` |
| documents | `BDD_Documents` |
| utilisateurs | `BDD_Utilisateurs` |
| connectivites | `BDD_Connectivites` |

- La clé API doit avoir les droits **lecture + écriture** sur ce document.
- Il faut **au moins un utilisateur** dans `BDD_Utilisateurs` avec `Droits` =
  `Administrateur` (sinon personne ne peut se connecter : les nouvelles
  inscriptions arrivent en statut `En attente`, bloqué).

> Comme on réutilise le même document Grist, ces prérequis sont déjà satisfaits.
> L'authentification se fait **par email seul** (sans mot de passe) ; le vrai
> contrôle d'accès est la table `BDD_Utilisateurs` — la garder propre.

---

## 9. Bascule (cutover) et retour arrière

- L'ancien et le nouveau serveur peuvent tourner **en parallèle** (ils pointent
  vers le même Grist). La bascule réelle se fait au niveau **DNS**.
- **Bascule** : faire pointer `tcd.francedatareseau.fr` vers le nouveau serveur,
  vérifier que tout fonctionne, puis communiquer la nouvelle URL aux utilisateurs.
- **Retour arrière** : il suffit de re-pointer le DNS vers l'ancien serveur — aucune
  donnée n'est perdue puisque tout vit dans Grist.
- Penser à abaisser le **TTL DNS** (ex. 300 s) quelques heures avant la bascule pour
  une propagation rapide.

---

## 10. Checklist de mise en production

- [ ] Docker + Docker Compose installés, ports 80/443 ouverts.
- [ ] DNS `tcd.francedatareseau.fr` → IP du nouveau serveur (`dig` OK).
- [ ] Dossier `app_form_fnccr/` complet copié sur le serveur.
- [ ] `.env` créé et rempli : `GRIST_API_KEY`, `GRIST_DOC_ID`, `SECRET_KEY`, `ENVIRONMENT=production`, `LE_EMAIL`.
- [ ] `docker compose up -d --build` lancé.
- [ ] `docker compose logs tcd` affiche **« Connexion Grist OK »**.
- [ ] `https://tcd.francedatareseau.fr` répond (page de login, certificat TLS valide).
- [ ] Connexion testée avec un compte `Administrateur` existant.
- [ ] (Si souhaité) variables `SMTP_*` renseignées pour les notifications email.

---

## 11. Dépannage rapide

| Symptôme | Piste |
|---|---|
| Logs : erreur de connexion Grist au démarrage | Vérifier `GRIST_API_KEY` / `GRIST_DOC_ID` et l'accès réseau sortant vers `grist.francedatareseau.fr`. |
| Pas de certificat TLS / erreur Caddy | Le DNS doit pointer vers ce serveur **avant** le 1er démarrage ; ports 80/443 ouverts ; `LE_EMAIL` renseigné. Voir `docker compose logs caddy`. |
| « Adresse email non reconnue » au login | Normal si l'utilisateur n'est pas dans `BDD_Utilisateurs`. Un admin doit l'ajouter / valider. |
| Sessions déconnectées à chaque redémarrage | `SECRET_KEY` non fixe dans le `.env`. |
| L'app répond mais en HTTP non sécurisé | `ENVIRONMENT=production` manquant, ou accès direct au port 8000 au lieu de passer par le proxy. |

---

*Pour le détail complet de l'application (architecture, sécurité, champs Grist),
voir `config_fdr.md` à la racine du projet.*
