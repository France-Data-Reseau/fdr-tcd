# Règles du projet — FNCCR Cartographie TCD V2

Application FastAPI/Jinja2 dont la base de données est un document **Grist**
(12 tables `BDD_*`, accès via pygrister). Architecture et décisions complètes :
`docs_architecture/`. Schéma Grist de référence : voir la documentation interne du schéma Grist.

## Règles absolues

1. **Ne jamais toucher** à l'app v1 (`app-v1.example.org`, service Docker `fdr`,
   `~/stack/app_form_fnccr` sur le VPS).
2. **Ne jamais modifier le schéma Grist** sans accord explicite de Victor.
   Toute migration passerait par l'API, jamais par l'interface (elle EFFACE les données).
3. **Aucun secret en dur** — tout vient du `.env` (voir `.env.example`).
4. **UX/UI strictement identique à la v1** (référence : l'UI de la v1).
   Tout changement visuel = à proposer à Victor, jamais imposé.

## Invariants d'architecture

- **Étanchéité des couches** : les idiomes Grist/pygrister — tuples
  `(status, data)`, listes `['L', id…]` — ne remontent JAMAIS au-dessus de
  `app/repositories/`. Les services manipulent des données propres.
- **Invalidation du cache** : déclenchée par les méthodes d'écriture de
  `repositories/base.py`, jamais par les services.
- **Mono-worker** : cache mémoire, jetons magic link consommés et compteurs de
  rate limiting reposent sur « 1 process ». Ne JAMAIS ajouter `--workers` au
  CMD uvicorn sans introduire un magasin partagé pour ces trois mécanismes.
- **Pas de transactions Grist** : les écritures multi-tables doivent être
  ordonnées pour minimiser les états incohérents, et journaliser l'état atteint
  en cas d'échec partiel.
- **Champs formule jamais écrits** (signalés dans `repositories/types.py`).
- **Droits en français uniquement** : `Administrateur`, `Editeur`, `Visiteur`,
  `Extention`, `En attente`. « Extention » (sic) est une **valeur de données
  Grist — ne pas corriger l'orthographe**, les contrôles d'accès en dépendent.
  Les valeurs anglaises héritées sont normalisées à la lecture, jamais écrites.
- **Erreurs sobres** : jamais de doc ID, d'URL Grist, de clé API ni de
  stacktrace dans les messages ou les logs orientés utilisateur.

## Vérification (avant tout commit / build de déploiement)

```bash
uv run ruff check app tests scripts
uv run pyright
uv run pytest
```

## Données

- Aucune donnée réelle (emails, téléphones du document Grist) dans les
  fixtures de tests — jeux synthétiques uniquement.
- L'API de restitution n'expose jamais les emails/téléphones des contacts.
