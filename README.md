# FNCCR — Formulaire de saisie Grist

Application web légère pour alimenter la base Grist de la FNCCR via des formulaires de saisie.

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

## Structure

```
├── main.py              # Routes FastAPI
├── grist_client.py      # Client API Grist
├── .env                 # Clé API (non versionné)
├── .env.example         # Template du .env
├── requirements.txt     # Dépendances Python
├── static/
│   └── style.css        # Styles CSS
└── templates/
    ├── base.html        # Layout de base
    ├── accueil.html     # Sélection de collectivité
    ├── collectivite.html# Fiche collectivité
    ├── projet_form.html # Création/modification de projet
    ├── cas_usage.html   # Sous-formulaire cas d'usage
    ├── partenaire.html  # Sous-formulaire partenaire
    ├── programme.html   # Sous-formulaire programme
    ├── document.html    # Sous-formulaire document
    └── contact.html     # Sous-formulaire contact
```

## Parcours utilisateur

1. **Accueil** — Rechercher et sélectionner une collectivité, ou en créer une nouvelle
2. **Fiche collectivité** — Modifier les infos, voir les projets liés
3. **Projet** — Créer ou modifier un projet, accéder aux sous-formulaires
4. **Sous-formulaires** — Ajouter des cas d'usage, partenaires, programmes, documents, contacts
