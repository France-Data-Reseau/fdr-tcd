# config_fdr.md — Prérequis & installation de l'app FNCCR

> Récapitulatif des prérequis pour installer et faire tourner l'application
> **Formulaire de saisie FNCCR** (FastAPI + Grist) sur un serveur.
> Conçu pour être **portable** : ce qui suit vaut pour le VPS `revorun.eu`
> comme pour n'importe quel autre hôte.
>
> 🔐 **Aucun secret en clair dans ce fichier.** Les vraies valeurs vivent
> dans le `.env` (non versionné) ou le gestionnaire de mots de passe.

---

## 1. Vue d'ensemble de l'application

| Élément | Détail |
|---|---|
| Type | Application web server-rendered (formulaire de saisie + restitution) |
| Stack | Python 3.11+, FastAPI, Uvicorn, Jinja2 |
| Entrée | `main.py` → objet ASGI `main:app` |
| Backend de données | **Grist externe** : `https://grist.francedatareseau.fr` (API REST) |
| Authentification | **Par email seul** (pas de mot de passe) — utilisateurs + droits gérés dans la table Grist `BDD_Utilisateurs` |
| Sessions | Cookies signés (Starlette `SessionMiddleware`), `Secure` activé si `ENVIRONMENT=production` |
| Sécurité applicative | En-têtes HTTP + CSP, protection CSRF, rate-limiting (slowapi) |
| Domaine cible (VPS) | `https://fdr.revorun.eu` |

> ⚠️ Le Grist utilisé est l'instance publique **`grist.francedatareseau.fr`**,
> et **non** le `grist.revorun.eu` du VPS. L'app n'a donc pas besoin du Grist
> local — juste d'un accès réseau sortant HTTPS vers `grist.francedatareseau.fr`.

---

## 2. Prérequis système

Deux modes d'installation possibles. Choisir **l'un** des deux :

### Mode A — Conteneurisé (recommandé, requis pour le VPS revorun.eu)
- **Docker** + **Docker Compose** (le stack du VPS est 100 % Docker).
- Un reverse proxy en façade pour le TLS (sur le VPS : **Caddy**).

### Mode B — Natif (machine de dev, ou serveur sans Docker)
- **Python 3.11 ou supérieur** (testé en 3.11.4).
- `pip` + `venv`.
- Optionnel : un reverse proxy (nginx/Caddy) + un superviseur (systemd) en prod.

### Réseau (dans les deux cas)
- **Accès sortant HTTPS** vers `grist.francedatareseau.fr` (port 443).
- **Ports publics** entrants : seulement via le reverse proxy (80/443). L'app
  elle-même écoute en interne sur **8000** (jamais exposé directement).

---

## 3. Dépendances Python

Listées dans [`requirements.txt`](requirements.txt) :

```
fastapi==0.115.6
uvicorn==0.34.0
jinja2==3.1.5
httpx==0.28.1
python-dotenv==1.0.1
python-multipart==0.0.20
itsdangerous==2.2.0
slowapi==0.1.9
```

Installation : `pip install -r requirements.txt`

---

## 4. Variables d'environnement (`.env`)

L'app lit sa config via `python-dotenv` (`load_dotenv()`) puis `os.getenv(...)`.
Créer un fichier `.env` à la racine (modèle dans [`.env.example`](.env.example)) :

| Variable | Obligatoire | Rôle | Comment l'obtenir / la générer |
|---|---|---|---|
| `GRIST_API_KEY` | ✅ | Jeton d'API Grist (Bearer) | Compte Grist → *Profile Settings* → *API Key*. **Secret.** |
| `GRIST_DOC_ID` | ✅ | ID du document Grist contenant les tables | Dans l'URL du doc Grist (`/docs/<DOC_ID>/...`) |
| `SECRET_KEY` | ✅ (prod) | Clé de signature des cookies de session | `python -c "import secrets; print(secrets.token_urlsafe(32))"` — **Secret, à fixer en prod** (sinon régénérée à chaque démarrage = sessions invalidées) |
| `ENVIRONMENT` | ⛳ (prod) | Active le flag `Secure` des cookies + HSTS | Mettre `production` derrière un reverse proxy HTTPS |

> 🔒 `GRIST_BASE_URL` est codé en dur dans `grist_client.py`
> (`https://grist.francedatareseau.fr`). À changer **uniquement** si on migre
> vers une autre instance Grist.

---

## 5. Prérequis côté Grist (backend de données)

L'app ne fonctionne **que** si le document Grist contient les tables attendues.

### Tables requises (clé interne → nom de table Grist)
| Clé | Table Grist |
|---|---|
| `collectivites` | `BDD_Collectivites` |
| `projets` | `BDD_Projets` |
| `contacts` | `BDD_Contacts` |
| `cas_d_usage` | `BDD_CasUsages` |
| `partenaires` | `BDD_Partenaires` |
| `programmes` | `BDD_Programmes` |
| `documents` | `BDD_Documents` |
| `utilisateurs` | `BDD_Utilisateurs` |
| `connectivites` | `BDD_Connectivites` |

### Accès & comptes
- La clé d'API (`GRIST_API_KEY`) doit avoir les droits **lecture + écriture** sur ce document.
- **Au moins un utilisateur** dans `BDD_Utilisateurs` avec le champ `Droits`
  réglé sur `Admin` (ou `Editeur`) — sinon impossible de se connecter
  (les nouvelles inscriptions arrivent en statut `En attente` et sont bloquées).
- Champs utilisateur lus par l'app : `Email`, `Prenom`, `Nom`, `Organisation`,
  `Droits`, `Collectivite`.

> ⚠️ Au démarrage, l'app appelle Grist (lifespan) pour charger/cacher les
> références. Sans connectivité ni clé valide, le démarrage logge une erreur de
> connexion Grist.

---

## 6. DNS / domaine

- Enregistrement **A** : `fdr.revorun.eu` → `51.89.22.185` (VPS OVH). ✅ *créé*
- Vérifier : `dig fdr.revorun.eu +short` doit retourner `51.89.22.185`.
- Le certificat TLS est obtenu automatiquement par Caddy (Let's Encrypt) à la
  première requête, une fois la route ajoutée au `Caddyfile`.

---

## 7. Installation — Mode B (natif, dev/local)

```bash
git clone <repo> app_form_fnccr && cd app_form_fnccr
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # puis renseigner les valeurs (section 4)
uvicorn main:app --reload     # dev → http://localhost:8000
# Prod sans Docker :
# uvicorn main:app --host 0.0.0.0 --port 8000
```

---

## 8. Installation — Mode A (Docker, VPS revorun.eu)

L'app n'est pas encore conteneurisée. Il faut **un `Dockerfile`** à la racine
(à committer dans le repo), puis l'intégrer au stack `~/stack/` du VPS comme un
service avec *build context* (même schéma que le dashboard *goeland*).

### 8.1 `Dockerfile` (à créer à la racine du projet)
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

> Ajouter aussi un `.dockerignore` (`.venv/`, `__pycache__/`, `.env`, `*.png`,
> `.git/`) pour ne pas embarquer de secrets ni de poids inutile.

### 8.2 Service dans `~/stack/docker-compose.yml`
```yaml
  fdr:
    build: ./app_form_fnccr        # code cloné/déposé dans ~/stack/app_form_fnccr
    container_name: fdr
    restart: unless-stopped
    env_file: ./app_form_fnccr/.env   # secrets hors compose
    environment:
      - ENVIRONMENT=production
    networks: [stack]
```

### 8.3 Route dans `~/stack/Caddyfile`
```caddyfile
fdr.revorun.eu {
    import security_headers
    reverse_proxy fdr:8000
    encode gzip
}
```

### 8.4 Mise en service
```bash
cd ~/stack
docker compose config                 # valider la syntaxe
docker compose up -d --build fdr      # build + démarrage
docker compose logs fdr --tail 50     # vérifier "Connexion Grist OK"
docker compose restart caddy          # charger la route + obtenir le cert TLS
curl -I https://fdr.revorun.eu        # 200 / 30x attendu
```

> Le `.env` (secrets) est déposé **manuellement** sur le serveur dans
> `~/stack/app_form_fnccr/.env` et **n'est jamais committé** (cf. `.gitignore`).

---

## 9. Checklist de mise en production

- [ ] DNS `fdr.revorun.eu` → IP du serveur résolu (`dig`).
- [ ] `.env` rempli : `GRIST_API_KEY`, `GRIST_DOC_ID`, `SECRET_KEY` (fixe), `ENVIRONMENT=production`.
- [ ] Document Grist accessible avec les 9 tables `BDD_*` et un utilisateur `Admin`.
- [ ] `Dockerfile` + `.dockerignore` présents (Mode A).
- [ ] Service `fdr` ajouté au compose + route Caddy ajoutée.
- [ ] `docker compose config` OK, conteneur *up*, logs propres ("Connexion Grist OK").
- [ ] TLS actif et `https://fdr.revorun.eu` répond (page de login).
- [ ] Connexion testée avec un compte `Admin`/`Editeur` existant.

---

## 10. Points de sécurité à ne pas oublier

- **`SECRET_KEY` fixe en prod** : sans valeur stable, chaque redémarrage
  invalide toutes les sessions ouvertes.
- **`ENVIRONMENT=production`** : impératif derrière HTTPS (cookies `Secure` + HSTS).
- **Ne jamais committer le `.env`** ni écrire les secrets dans le compose / Caddyfile.
- **Port 8000 jamais exposé publiquement** : accès uniquement via le reverse proxy.
- L'auth reposant sur l'email seul, la **maîtrise de la table `BDD_Utilisateurs`**
  (qui a `Droits`) est le vrai contrôle d'accès — la garder propre.

---

## 11. Pour porter l'app sur un autre serveur (résumé express)

1. Cloner le repo + créer le `.env` (section 4).
2. Pointer un sous-domaine vers le nouvel hôte (section 6).
3. Mode A : `docker compose up -d --build` derrière un reverse proxy TLS.
   Mode B : `venv` + `uvicorn main:app --host 0.0.0.0 --port 8000` + systemd.
4. Vérifier la connexion Grist au démarrage et tester le login.

> Les seules dépendances externes sont : **l'instance Grist** (données + comptes)
> et **un accès réseau sortant HTTPS**. Aucune base de données locale à provisionner.
