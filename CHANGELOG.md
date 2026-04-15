# Changelog — App Form FNCCR

## État au 2026-04-02

Commit initial : **2026-03-06** — `Initial commit - FNCCR form app (FastAPI + Grist)`

Toutes les modifications ci-dessous sont des changements non commités apportés depuis le commit initial.

---

## Sécurité

### Authentification & Sessions
- Ajout d'un système de login / inscription / logout complet (`/login`, `/inscription`, `/logout`)
- Session sécurisée via `SECRET_KEY` (chargée depuis `.env`, ou générée aléatoirement au démarrage)
- Cookie de session avec `same_site="lax"`, durée limitée à 1 heure, `https_only` en production
- Gestion des droits utilisateurs : `Administrateur`, `Editeur`, `Visiteur`, `Extention`, `En attente`
- Page `/acces-refuse` pour les comptes en attente de validation
- Helpers `require_auth()` et `require_editor()` pour protéger les routes

### CSRF
- Génération et vérification d'un token CSRF sur toutes les soumissions de formulaires (`get_csrf_token`, `verify_csrf`)
- Champ caché `csrf_token` injecté dans tous les formulaires HTML

### Headers HTTP
- Nouveau middleware `SecurityHeadersMiddleware` ajoutant :
  - `X-Frame-Options: SAMEORIGIN`
  - `X-Content-Type-Options: nosniff`
  - `Content-Security-Policy` (whitelist CDN, API adresse)
  - `Referrer-Policy`, `Permissions-Policy`
  - `Strict-Transport-Security` (en production uniquement)

### Rate Limiting
- Intégration de `slowapi` (ajouté dans `requirements.txt`)
- Limitation à 10 requêtes/minute sur la route POST `/login`

---

## Nouvelles fonctionnalités

### Authentification Grist
- `grist_client.py` : `get_user_by_email()` — recherche d'un utilisateur dans `BDD_Utilisateurs`
- `grist_client.py` : `create_user()` — création d'un nouvel utilisateur

### Contrôle d'accès aux projets
- Nouvelle fonction `verify_projet_access()` : vérifie qu'un utilisateur `Editeur` accède uniquement aux projets de sa collectivité

### Géocodage
- `grist_client.py` : `geocode_address()` — géocodage d'une adresse via l'API `api-adresse.data.gouv.fr`
- `grist_client.py` : `_geocode_batch()` — géocodage en batch (plusieurs adresses en parallèle)

### Page Menu
- Nouveau template `templates/menu.html` — page d'accueil après connexion avec navigation par boutons
- Route `GET /` (refactorisée) renvoyant vers le menu

### Page Restitution
- Nouveau template `templates/restitution.html` — tableau de bord de visualisation des données
- Route `GET /restitution` — page de restitution (accès `Visiteur` et au-dessus)
- Route `GET /api/restitution/donnees` — API JSON fournissant les données agrégées pour la restitution
- `grist_client.py` : `get_restitution_data()` — agrégation des données avec cache

### Page Complétion
- Route `GET /completion` — indicateur de complétion du dossier (filtrée par collectivité pour les `Editeur`)

### Demande de modification de droits
- Route `POST /demande-modification` — permet à un utilisateur `En attente` de soumettre une demande

---

## Améliorations des formulaires

### Formulaires existants
- Tous les formulaires utilisent désormais `grist_field()` pour l'affichage pré-rempli (lecture propre des champs Grist)
- `projet_form.html` : ajout du champ CSRF, texte d'aide, sélection pré-remplie via `grist_field`
- `cas_usage.html`, `contact.html`, `document.html`, `partenaire.html`, `programme.html` : ajout CSRF + pré-remplissage

### Helper `get_field_value`
- `grist_client.py` : nouvelle fonction `get_field_value(record, field)` — extraction propre d'une valeur de champ Grist (gère les références, listes, etc.)
- Exposée dans les templates via `templates.env.globals["grist_field"]`

### Helper `safe_int`
- Conversion sécurisée de valeurs en entier, utilisée pour les IDs Grist

---

## Interface (CSS)

### Nouvelles sections dans `static/style.css` (+1 351 lignes)
- **Header** : affichage du nom/badge utilisateur connecté
- **Login** : mise en page de la page de connexion (`.login-wrapper`, `.login-subtitle`)
- **Menu** : grille de boutons de navigation (`.menu-card`, `.menu-btn`, `.menu-btn-accent`)
- **Restitution** : layout complet (topbar, stats row, sidebar filtres, tableau projets)
- **Carte** : styles pour la carte interactive et les popups
- **Distributions & Charts** : pie charts, jauges d'avancement
- **Badges** : `.badge`, `.badge-pending`, `.sous-section`
- **Tabs, Filtres** : composants de navigation par onglets et filtres latéraux
- **Cas d'usage** : affichage emoji et checkboxes thématiques

---

## Configuration

- `.env.example` : ajout de `SECRET_KEY` et `GRIST_DOC_ID` comme variables à configurer
- `README.md` : mise à jour complète (+194 lignes)

---

## Nouveaux templates

| Fichier | Description |
|---|---|
| `templates/login.html` | Page de connexion |
| `templates/inscription.html` | Page d'inscription |
| `templates/acces_refuse.html` | Page accès refusé (compte en attente) |
| `templates/menu.html` | Menu principal post-connexion |
| `templates/restitution.html` | Tableau de bord de visualisation |
