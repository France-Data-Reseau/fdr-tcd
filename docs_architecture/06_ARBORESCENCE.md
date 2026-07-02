# 06. Arborescence et rôle des fichiers

Ce document récapitule l'organisation du code source de l'application FNCCR Cartographie TCD V2. L'architecture respecte une stricte séparation des responsabilités entre la présentation (API/Templates), la logique métier (Services) et l'accès aux données (Repositories).

## 📁 À la racine du projet

- **`AGENTS.md`** : Règles fondamentales et invariants du projet, spécifiquement rédigées pour cadrer le comportement des assistants IA (Claude, Cursor, etc.).
- **`MAINTENANCE.md`** : Documentation opérationnelle pour maintenir l'application.
- **`Dockerfile`** & **`.dockerignore`** : Configuration pour conteneuriser l'application (pour le déploiement sur le VPS).
- **`pyproject.toml`** & **`uv.lock`** : Gestion des dépendances Python via l'outil `uv`.
- **`.env.example`** : Modèle des variables d'environnement requises (URL Grist, clés secrètes, configuration SMTP, etc.).
- **`main.py`** *(dans `app/`)* : Point d'entrée de l'application FastAPI. Il est volontairement fin (enregistrement des middlewares, des routes et gestion globale des erreurs).

## 📁 `docs_architecture/`
Contient l'intégralité de la documentation technique et des décisions d'architecture :
- **`00_SYNTHESE.md`** : Vue d'ensemble du projet.
- **`01_ARCHITECTURE.md`** : Explication des couches (API > Service > Repository).
- **`02_AUTHENTIFICATION.md`** : Modes d'auth (mot de passe, magic link, SSO) et sessions.
- **`03_SECURITE.md`** : Protections contre les vulnérabilités (IDOR, CSRF, Rate Limiting).
- **`04_TESTS.md`** : Stratégie de tests.
- **`05_DEPLOIEMENT.md`** : Déploiement sur le serveur.
- **`06_ARBORESCENCE.md`** : Ce fichier.
- **`07_STRATEGIE_AUTH.md`** : Stratégie multi-mode et migration entre modes d'authentification.
- **`08_OPERATIONS_VPS.md`** : Runbook pour piloter le VPS depuis un Mac (accès SSH, opérations, déploiement).
- **`09_RENOMMAGE_COLONNES_GRIST.md`** : Extract des colonnes Grist + proposition de renommage propre (tâche différée).

## 📁 `app/` - Cœur de l'application

L'application est découpée en 4 sous-dossiers principaux et 2 fichiers centraux.

### Fichiers centraux
- **`main.py`** : Déclaration de l'application FastAPI, montage des fichiers statiques, et branchement des exceptions.
- **`dependencies.py`** : Moteur d'injection de dépendances (`get_projet_service()`, etc.) sous forme de singletons en mémoire, et fonctions de contrôle d'accès (`require_auth`, `require_editor`, protections anti-IDOR).

### 1. `app/api/` (Couche de Présentation / Routeurs)
Contient les endpoints FastAPI. Leur rôle est d'intercepter les requêtes HTTP, de lire les formulaires/paramètres, d'appeler les *Services*, et de renvoyer une page HTML (Jinja) ou une redirection. **Aucune logique métier ne s'y trouve.**
- **`auth.py`** : Routes de connexion (login, vérification du magic link, déconnexion).
- **`projets.py`** : Création et modification des fiches projets.
- **`collectivites.py`** : Affichage et édition du profil des collectivités.
- **`sous_objets.py`** : Gestion des entités liées aux projets (cas d'usage, partenaires, etc.).
- **`restitution.py`** : API JSON pour l'affichage de la carte publique.
- **`admin.py`** : Interface d'administration pour gérer les utilisateurs.
- **`menu.py`** : Routes de navigation simples (accueil, etc.).
- **`completion.py`** : Routes utilitaires (auto-complétion).

### 2. `app/services/` (Couche de Logique Métier)
Contient le "cerveau" de l'application. Les services manipulent des données propres envoyées par les routeurs, appliquent les règles métier, et orchestrent les écritures/lectures via les *Repositories*.
- **`types.py`** : Modèles de données Pydantic (Formulaires validés) partagés entre l'API et les services.
- **`projet_service.py`** : Logique de création de projet (liaison avec la collectivité, fallback en cas d'erreur).
- **`auth_service.py`** & **`magic_link_service.py`** : Génération des jetons, envoi d'emails, limitation de cadence (rate limiting) par adresse email.
- **`collectivite_service.py`** : Synthèse des données d'une collectivité.
- **`restitution_service.py`** : Agrége et formate les données complexes pour les renvoyer à la carte V1.
- **`geo_service.py`** & **`geocode_client.py`** : Gestion des appels d'API externes pour géocoder les adresses.
- **`notification_service.py`** : Gestion de l'envoi des emails via SMTP.
- **`admin_service.py`** : Gestion des droits utilisateurs.

### 3. `app/repositories/` (Couche d'Accès aux Données / Grist)
Couche d'abstraction hermétique pour dialoguer avec la base de données Grist via `pygrister`.
- **`base.py`** : Le cœur de l'accès aux données. Fournit le CRUD générique (`list_all`, `create`, `update`), gère les `RefList` propres à Grist, traduit les erreurs réseau en exceptions propres, et gère l'invalidation du cache.
- **`cache.py`** : Cache TTL en mémoire (stockage des tables Grist pendant 5 minutes) pour accélérer les lectures et limiter les appels API Grist.
- **`grist_session.py`** : Initialisation du client Grist.
- **`types.py`** : Définition de tous les `TypedDict` représentant le schéma exact des tables Grist (ex: `ProjetRecord`, `UtilisateurRecord`).
- **`*_repository.py`** (ex: `projet_repository.py`, `contact_repository.py`) : Implémentations spécifiques pour chaque table, héritant de `BaseGristRepository`.

### 4. `app/core/` (Utilitaires de Base)
- **`config.py`** : Chargement et validation des variables d'environnement (`.env`) via Pydantic Settings.
- **`security.py`** : Middlewares de sécurité (Headers HTTP stricts), limitation de débit IP (SlowAPI), et gestion des tokens CSRF.
- **`templating.py`** : Configuration du moteur de rendu Jinja2.
- **`flash.py`** : Gestion des "Flash messages" (messages de succès/erreur qui s'affichent une seule fois après une redirection).

## 📁 Autres dossiers

### `templates/`
Contient toutes les vues HTML de l'application, utilisant la syntaxe Jinja2. Elles sont conçues pour être visuellement identiques à l'application V1 (héritage de base, macros pour les champs de formulaires, etc.).

### `static/`
Actifs statiques servis directement aux clients : feuilles de style CSS, scripts JavaScript côté client (Alpine.js, requêtes asynchrones), images et logos.

### `scripts/`
Scripts utilitaires administratifs (non exécutés par le serveur web) :
- **`check_grist_schema.py`** : Script très important qui compare le schéma de la base Grist distante avec le schéma attendu par le code, pour détecter les dérives (champs renommés ou supprimés).
- **`export_grist.py`** / **`import_*.py`** : Outils pour extraire ou injecter des données (souvent utilisé pour les migrations manuelles ou les environnements de test).

### `tests/`
Suite complète de tests automatisés (Pytest).
- **`conftest.py`** : Configuration et *fixtures* Pytest (simulation d'une base Grist, clients de test).
- **`test_*.py`** : Les tests unitaires et d'intégration validant le comportement des différentes couches, en insistant sur la sécurité (anti-IDOR, CSRF) et la conformité au comportement attendu.

### `KIT_REBUILD_V2/`
Dossier contenant le matériel de référence pour la refonte V2. À ne pas utiliser en production, c'est un point d'appui historique. Contient le `.grist` original et le `SCHEMA_GRIST.md` de référence.
