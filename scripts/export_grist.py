"""Export daté du document Grist (sauvegarde — exigence D1 des revues).

Produit dans ``exports_grist/`` (gitignoré) :
- ``fdr_<date>.grist`` : le document complet (SQLite), restaurable tel quel ;
- ``fdr_<date>_<table>.xlsx`` : un classeur par table (lecture humaine).

À lancer AVANT : le go-live, tout script d'écriture de masse (ex. nettoyage
des droits), toute migration de schéma.

Usage : uv run python -m scripts.export_grist
"""

import logging
import sys
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TABLES = [
    "BDD_CasUsages", "BDD_Collectivites", "BDD_Connectivites",
    "BDD_Contrats", "BDD_Departements", "BDD_Documents", "BDD_Partenaires",
    "BDD_Programmes", "BDD_Projets", "BDD_Solutions", "BDD_Utilisateurs",
]


def main() -> int:
    from app.dependencies import get_grist_api

    grist = get_grist_api()
    horodatage = datetime.now().strftime("%Y%m%d_%H%M")
    dossier = Path("exports_grist")
    dossier.mkdir(exist_ok=True)

    echecs = 0

    cible = dossier / f"fdr_{horodatage}.grist"
    status, _ = grist.download_sqlite(cible)
    if status < 300:
        logger.info("Document complet exporté : %s", cible)
    else:
        logger.error("Échec export .grist (HTTP %s)", status)
        echecs += 1

    for table in TABLES:
        cible = dossier / f"fdr_{horodatage}_{table}.xlsx"
        status, _ = grist.download_excel(cible, table)
        if status < 300:
            logger.info("Table exportée : %s", cible)
        else:
            logger.error("Échec export %s (HTTP %s)", table, status)
            echecs += 1

    if echecs:
        logger.error("%d export(s) en échec — sauvegarde INCOMPLÈTE", echecs)
        return 1
    logger.info("Sauvegarde complète dans %s/", dossier)
    return 0


if __name__ == "__main__":
    sys.exit(main())
