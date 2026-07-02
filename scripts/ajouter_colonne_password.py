"""Ajoute la colonne `password_hash` à BDD_Utilisateurs (auth par mot de passe).

Modification de SCHÉMA via l'API Grist — JAMAIS l'interface (qui efface les
données, piège n°1). À lancer UNE fois, **après un export de sauvegarde**
(`scripts/export_grist.py`) et **avant** de déployer le code d'auth par mot de
passe. Idempotent : ne fait rien si la colonne existe déjà. N'affecte pas la
v1 (une colonne supplémentaire est ignorée par une app qui lit des colonnes
nommées).

Usage (sur le VPS, dans le conteneur, là où vivent les vraies clés) :
    docker compose exec fdr2 python -m scripts.ajouter_colonne_password
"""

import logging
import sys

from app.repositories.types import COL_PASSWORD_HASH, TABLE_UTILISATEURS

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    from app.dependencies import get_grist_api

    grist = get_grist_api()

    status, cols = grist.list_cols(TABLE_UTILISATEURS, hidden=True)
    if status >= 300:
        logger.error("Impossible de lire les colonnes de %s (HTTP %s)",
                     TABLE_UTILISATEURS, status)
        return 1
    if any(c.get("id") == COL_PASSWORD_HASH for c in cols):
        logger.info("Colonne '%s' déjà présente — rien à faire", COL_PASSWORD_HASH)
        return 0

    status, resultat = grist.add_cols(
        TABLE_UTILISATEURS,
        [{"id": COL_PASSWORD_HASH,
          "fields": {"label": COL_PASSWORD_HASH, "type": "Text"}}],
    )
    if status >= 300:
        logger.error("Échec de l'ajout de la colonne (HTTP %s) : %s", status, resultat)
        return 1
    logger.info("Colonne ajoutée à %s : %s", TABLE_UTILISATEURS, resultat)
    return 0


if __name__ == "__main__":
    sys.exit(main())
