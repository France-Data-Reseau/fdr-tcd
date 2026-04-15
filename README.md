# FNCCR — Cartographie des Usages TCD des Collectivites

Application web pour alimenter et visualiser la base Grist de la FNCCR (Federation Nationale des Collectivites Concedantes et Regies). Elle permet la saisie de donnees via des formulaires et la restitution cartographique interactive des projets de Territoires Connectes Durables (TCD).

## Fonctionnalites principales

- **Authentification et gestion des droits** — Systeme de roles (Administrateur, Editeur, Visiteur, Extention, En attente) avec inscription, validation par un administrateur, et demande d'elevation de droits
- **Saisie de donnees** — Formulaires de creation/modification de collectivites, projets, cas d'usage, partenaires, programmes, documents et contacts
- **Cartographie interactive** — Carte Leaflet.js avec marqueurs geolocalises, filtres multi-criteres, graphiques de repartition (donut charts CSS)
- **Fiches projet detaillees** — Popup modale affichant description, metadonnees, domaines, cas d'usage, partenaires, programmes et documents
- **Onglet "Ma Collectivite"** — Vue dediee avec logo, statistiques et projets de la collectivite de l'utilisateur connecte

## Pile technique

| Composant | Technologie |
|-----------|-------------|
| Backend | Python 3.11+, FastAPI, Uvicorn |
| Templates | Jinja2 |
| Base de donnees | Grist (API REST) |
| HTTP async | httpx |
| Sessions | Starlette SessionMiddleware |
| Frontend | HTML/CSS/JS vanilla, Leaflet.js |
| Geocodage | api-adresse.data.gouv.fr |

## Installation

```bash
pip install -r requirements.txt
cp .env.example .env
# Remplir GRIST_API_KEY dans .env
```

## Lancement

```bash
uvicorn main:app --reload
```

L'application sera accessible sur [http://localhost:8000](http://localhost:8000).

## Structure du projet

```
├── main.py              # Routes FastAPI, authentification, logique metier
├── grist_client.py      # Client API Grist (CRUD, cache, geocodage, restitution)
├── data_lists.py        # Listes de reference (departements, regions, connectivites)
├── .env                 # Cle API Grist (non versionne)
├── .env.example         # Template du .env
├── requirements.txt     # Dependances Python
├── static/
│   ├── style.css        # Styles CSS (layout, composants, responsive, modal)
│   └── logo.jpg         # Logo FNCCR
└── templates/
    ├── base.html            # Layout de base (header, footer, flash messages)
    ├── login.html           # Page de connexion (par email)
    ├── inscription.html     # Formulaire d'inscription
    ├── acces_refuse.html    # Page d'attente / acces refuse
    ├── menu.html            # Menu principal (selon droits)
    ├── accueil.html         # Selection de collectivite (completion)
    ├── collectivite.html    # Fiche collectivite (creation/edition)
    ├── projet_form.html     # Formulaire projet
    ├── cas_usage.html       # Sous-formulaire cas d'usage
    ├── partenaire.html      # Sous-formulaire partenaire
    ├── programme.html       # Sous-formulaire programme
    ├── document.html        # Sous-formulaire document
    ├── contact.html         # Sous-formulaire contact
    └── restitution.html     # Page cartographie / restitution
```

## Systeme de droits

| Role | Completion (saisie) | Cartographie (consultation) | Administration |
|------|---------------------|-----------------------------|----------------|
| **Administrateur** | Toutes collectivites | Oui | Gestion des utilisateurs dans Grist |
| **Editeur** | Sa collectivite uniquement | Oui | — |
| **Visiteur** | Non (bouton grise) | Oui | Peut demander l'elevation a Editeur |
| **Extention** | Non | Oui | Demande d'elevation en cours |
| **En attente** | Non | Non | Compte en attente de validation |

**Parcours de demande d'elevation** : Un Visiteur clique sur "Demande de modification" dans le menu. Son statut passe a "Extention". Un administrateur peut alors manuellement passer son statut a "Editeur" dans la table `BDD_Utilisateurs` de Grist.

## Parcours utilisateur

1. **Connexion** — Saisir son email. Si inconnu, redirection vers l'inscription.
2. **Inscription** — Remplir ses informations et choisir sa collectivite. Le compte est cree en "En attente".
3. **Menu principal** — Acces a la Cartographie et/ou a la Completion selon les droits.
4. **Completion** — Selectionner ou creer une collectivite, puis saisir/modifier les projets et sous-elements.
5. **Cartographie** — Visualiser la carte, filtrer par criteres, consulter les fiches projet.

## Page de restitution (Cartographie)

La page de restitution offre une vue complete des donnees :

- **Carte Leaflet** avec marqueurs proportionnels au nombre de projets. Clic sur un marqueur pour voir les projets de la collectivite.
- **Filtres** (colonne gauche) : departement, connectivite, domaine, avancement. Mise a jour en temps reel de la carte et du tableau.
- **Cas d'usage** (colonne droite) : affichage des cas d'usage filtres sous forme de pills.
- **Graphiques** : repartition par connectivite, domaine, type de collectivite, avancement (donut charts en CSS `conic-gradient`).
- **Onglet "Ma Collectivite"** : vue personnalisee avec logo, statistiques et liste des projets.
- **Popup modale projet** : fiche complete avec description, grille de metadonnees, domaines, cas d'usage, partenaires, programmes et documents.

---

## Adapter l'application a une autre base Grist

Ce guide permet de dupliquer et adapter l'application pour une autre base de donnees Grist, y compris en utilisant le vibecoding (generation de code assistee par IA).

### 1. Preparer votre base Grist

Creez un document Grist avec les tables suivantes (les noms doivent correspondre au mapping dans `grist_client.py`) :

| Cle interne | Nom de table Grist | Champs principaux |
|-------------|--------------------|--------------------|
| `collectivites` | `BDD_Collectivites` | `nom`, `siren`, `statut`, `couverture`, `num_dep`, `dep`, `reg`, `site_web`, `adresse`, `url_logo`, `projet_s_` (RefList) |
| `projets` | `BDD_Projets` | `nom`, `description`, `avancement`, `echelle`, `domaine_s_` (ChoiceList), `connectivite_s_` (ChoiceList), `collectivite_s_porteuse_s_` (RefList), `region`, `mutualisation`, `soutien`, `contrat` |
| `cas_d_usage` | `BDD_CasUsages` | `nom`, `theme` (Choice), `projets` (Reference) |
| `partenaires` | `BDD_Partenaires` | `nom`, `role_s_` (ChoiceList), `Projets` (RefList) |
| `programmes` | `BDD_Programmes` | `nom`, `echelle`, `projet_s_` (RefList) |
| `documents` | `BDD_Documents` | `titre`, `type`, `projet` (Reference) |
| `contacts` | `BDD_Contacts` | `nom`, `prenom`, `email`, `telephone`, `fonction` |
| `utilisateurs` | `BDD_Utilisateurs` | `Email`, `Prenom`, `Nom`, `Organisation`, `Droits` (Choice: Administrateur/Editeur/Visiteur/Extention/En attente), `Collectivite` (Reference) |

### 2. Configurer l'application

1. Copiez le projet et installez les dependances :
   ```bash
   git clone <url-du-repo>
   cd app_form_fnccr
   pip install -r requirements.txt
   ```

2. Creez votre fichier `.env` :
   ```
   GRIST_API_KEY=votre_cle_api_grist
   ```

3. Modifiez les constantes de connexion dans `grist_client.py` :
   ```python
   GRIST_BASE_URL = "https://votre-instance-grist.example.com"
   GRIST_DOC_ID = "votre_doc_id_ici"
   ```

### 3. Adapter le mapping des tables

Si vos tables ont des noms differents, modifiez le dictionnaire `mapping` dans la fonction `init_tables()` de `grist_client.py` :

```python
mapping = {
    "collectivites": "VotreNomDeTable_Collectivites",
    "projets": "VotreNomDeTable_Projets",
    # ... etc.
}
```

### 4. Adapter les champs

Les noms de champs Grist sont utilises partout dans le code. Si vos champs ont des noms differents :

- **`grist_client.py`** : Modifiez les references aux champs dans `init_choices()`, `get_restitution_data()`, et les fonctions CRUD.
- **`main.py`** : Modifiez `_extract_collectivite_fields()`, `_extract_projet_fields()`, et les templates de contexte.
- **Templates** : Modifiez les references `record.fields.nom_du_champ` dans les fichiers HTML.

**Conseil vibecoding** : Donnez a l'IA la structure exacte de votre base Grist (noms de tables, noms de colonnes, types) et demandez-lui de mettre a jour tous les fichiers en consequence. L'IA peut effectuer un search-and-replace intelligent sur l'ensemble du projet.

### 5. Adapter les listes de reference

Le fichier `data_lists.py` contient les listes de departements, regions et connectivites francaises. Si votre contexte est different :

- Remplacez les listes `DEPARTEMENTS`, `REGIONS` et `CONNECTIVITES` par vos propres donnees.
- Le mapping `DEP_NUM_TO_REGION` sert a l'auto-completion dans les formulaires ; adaptez-le a votre logique de rattachement.

### 6. Personnaliser l'apparence

- **Logo** : Remplacez `static/logo.jpg`
- **Titre** : Modifiez `templates/base.html` (balise `<h1>` du header)
- **Couleurs** : Modifiez les variables CSS dans `static/style.css` (section `:root`)
- **Textes** : Les labels et textes sont en francais directement dans les templates

### 7. Deploiement

L'application est une app Python standard deployable sur tout hebergement supportant Python :

```bash
# Production avec Uvicorn
uvicorn main:app --host 0.0.0.0 --port 8000

# Ou avec Gunicorn + Uvicorn workers
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

**Important** : Changez la `secret_key` du `SessionMiddleware` dans `main.py` avant de deployer en production.

### Conseils pour le vibecoding

Si vous utilisez un assistant IA (Claude, ChatGPT, Cursor, etc.) pour adapter ce projet :

1. **Partagez la structure de votre base Grist** : Exportez les noms de tables et colonnes, les types de champs (Text, Choice, ChoiceList, Reference, RefList), et quelques exemples de donnees.
2. **Procedez par etape** : Commencez par le backend (`grist_client.py` puis `main.py`), puis les templates, puis le CSS.
3. **Testez apres chaque modification** : Lancez le serveur avec `--reload` et verifiez que les pages se chargent sans erreur.
4. **Utilisez les logs** : L'application log toutes les requetes Grist. Consultez la console pour identifier les erreurs de noms de champs ou de tables.
5. **Gardez le fichier `grist_client.py` comme source de verite** : C'est le seul fichier qui communique avec Grist. Toutes les adaptations de schema partent de la.
