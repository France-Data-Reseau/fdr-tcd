"""Extrait les colonnes (id, type, formule) de chaque table BDD_* — LECTURE SEULE.

Sert à préparer le nettoyage des noms de colonnes Grist (état réel exact, y
compris les formules à mettre à jour lors d'un renommage). N'écrit rien.

Usage (sur le VPS) :
    docker compose cp scripts/extract_colonnes.py fdr2:/app/scripts/extract_colonnes.py
    docker compose exec -T fdr2 python -m scripts.extract_colonnes
"""

import json
import sys

from app.repositories.types import (
    TABLE_CAS_USAGES,
    TABLE_COLLECTIVITES,
    TABLE_CONNECTIVITES,
    TABLE_CONTACTS,
    TABLE_CONTRATS,
    TABLE_DEPARTEMENTS,
    TABLE_DOCUMENTS,
    TABLE_PARTENAIRES,
    TABLE_PROGRAMMES,
    TABLE_PROJETS,
    TABLE_SOLUTIONS,
    TABLE_UTILISATEURS,
)

TABLES = [
    TABLE_CAS_USAGES, TABLE_COLLECTIVITES, TABLE_CONNECTIVITES, TABLE_CONTACTS,
    TABLE_CONTRATS, TABLE_DEPARTEMENTS, TABLE_DOCUMENTS, TABLE_PARTENAIRES,
    TABLE_PROGRAMMES, TABLE_PROJETS, TABLE_SOLUTIONS, TABLE_UTILISATEURS,
]


def main() -> int:
    from app.dependencies import get_grist_api

    grist = get_grist_api()
    resultat: dict = {}
    for table in TABLES:
        status, cols = grist.list_cols(table, hidden=True)
        if status >= 300:
            resultat[table] = {"erreur": status}
            continue
        colonnes = []
        for c in cols:
            f = c.get("fields", {})
            colonnes.append({
                "id": c.get("id"),
                "type": f.get("type"),
                "formule": bool(f.get("isFormula") and f.get("formula")),
                "formula_src": f.get("formula", "") if f.get("isFormula") else "",
            })
        resultat[table] = colonnes
    print(json.dumps(resultat, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
