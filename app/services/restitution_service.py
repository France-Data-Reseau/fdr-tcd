"""Agrégation des données de restitution (carte, donuts, pills, tableau).

Structure JSON STRICTEMENT identique à la v1 (le JS de la page en dépend) :
``{collectivites: [{id, nom, …, lat, lng, projets: […]}], stats: {…}, filtres: {…}}``.

- Les 8 tables sont chargées EN PARALLÈLE (asyncio.to_thread + gather) ; le
  cache TTL des repositories absorbe l'essentiel des appels et est invalidé
  par les écritures → le payload est toujours frais sans cache dédié.
- Coordonnées : lues depuis Grist (lat/long stockés) en priorité ; seules les
  collectivités sans coordonnées passent par le géocodage (sémaphore 5,
  résultats cachés dans le GeocodeClient pour la durée du processus).
- AUCUNE donnée de contact (emails/téléphones) dans le payload — parité v1
  et exigence anti-exfiltration.
"""

import asyncio
from typing import Any

from app.repositories.base import extract_values, first_value, ref_ids
from app.repositories.cas_usage_repository import CasUsageRepositoryProtocol
from app.repositories.collectivite_repository import CollectiviteRepositoryProtocol
from app.repositories.document_repository import DocumentRepositoryProtocol
from app.repositories.partenaire_repository import PartenaireRepositoryProtocol
from app.repositories.programme_repository import ProgrammeRepositoryProtocol
from app.repositories.projet_repository import ProjetRepositoryProtocol
from app.repositories.reference_repository import ReferenceRepositoryProtocol
from app.services.geo_service import GeoResolver
from app.services.geocode_client import GeocodeClient, stored_coords

_GEOCODE_PARALLELISME = 5


class RestitutionService:
    def __init__(
        self,
        collectivites: CollectiviteRepositoryProtocol,
        projets: ProjetRepositoryProtocol,
        cas_usages: CasUsageRepositoryProtocol,
        partenaires: PartenaireRepositoryProtocol,
        programmes: ProgrammeRepositoryProtocol,
        documents: DocumentRepositoryProtocol,
        references: ReferenceRepositoryProtocol,
        geocode: GeocodeClient,
    ):
        self._collectivites = collectivites
        self._projets = projets
        self._cas_usages = cas_usages
        self._partenaires = partenaires
        self._programmes = programmes
        self._documents = documents
        self._references = references
        self._geocode = geocode

    async def build_payload(self) -> dict:
        # Chargement parallèle des tables (sync pygrister → threads)
        (
            collectivites, projets, cas_usages, partenaires,
            programmes, documents, connectivites, departements,
        ) = await asyncio.gather(
            asyncio.to_thread(self._collectivites.list_all),
            asyncio.to_thread(self._projets.list_all),
            asyncio.to_thread(self._cas_usages.list_all),
            asyncio.to_thread(self._partenaires.list_all),
            asyncio.to_thread(self._programmes.list_all),
            asyncio.to_thread(self._documents.list_all),
            asyncio.to_thread(self._references.list_connectivites),
            asyncio.to_thread(self._references.list_departements),
        )

        conn_by_id = {r["id"]: str(r.get("nom") or "") for r in connectivites}
        dep_by_id = {r["id"]: str(r.get("nom") or "") for r in departements}
        projets_by_id = {p["id"]: p for p in projets}

        # Index cas d'usage par projet (un cas peut être lié à PLUSIEURS projets)
        cas_by_projet: dict[int, list[dict]] = {}
        for cu in cas_usages:
            themes = extract_values(cu.get("theme"))
            cas_item = {
                "nom": str(cu.get("nom") or ""),
                "theme": themes[0] if themes else "",
            }
            for pid in ref_ids(cu.get("projets")):
                cas_by_projet.setdefault(pid, []).append(cas_item)

        # Index partenaires par projet
        part_by_projet: dict[int, list[dict]] = {}
        for pa in partenaires:
            for pid in ref_ids(pa.get("projets")):
                part_by_projet.setdefault(pid, []).append(
                    {"nom": str(pa.get("nom") or ""), "role": pa.get("roles", "")}
                )

        # Index programmes par projet
        prog_by_projet: dict[int, list[dict]] = {}
        for pr in programmes:
            for pid in ref_ids(pr.get("projets")):
                prog_by_projet.setdefault(pid, []).append(
                    {"nom": str(pr.get("nom") or "")}
                )

        # Index documents par projet (Ref simple)
        doc_by_projet: dict[int, list[dict]] = {}
        for d in documents:
            pid = d.get("projet")
            if isinstance(pid, int) and pid:
                doc_by_projet.setdefault(pid, []).append(
                    {"titre": str(d.get("titre") or ""), "type": d.get("type", "")}
                )

        # Collectivité → IDs projets (RefList directe + recherche inverse)
        coll_projet_ids: dict[int, set[int]] = {}
        for c in collectivites:
            coll_projet_ids[c["id"]] = set(ref_ids(c.get("projets")))
        for p in projets:
            for cid in ref_ids(p.get("collectivites_porteuses")):
                coll_projet_ids.setdefault(cid, set()).add(p["id"])

        # Résolution géographique (coordonnées stockées prioritaires)
        geo_results = await self._resolve_coords(collectivites, dep_by_id)

        result_collectivites: list[dict] = []
        for c in collectivites:
            pid_set = coll_projet_ids.get(c["id"], set())
            c_projets: list[dict] = []
            for pid in pid_set:
                projet = projets_by_id.get(pid)
                if projet is None:
                    continue
                c_projets.append(
                    {
                        "id": pid,
                        "nom": str(projet.get("nom") or ""),
                        "domaine": extract_values(projet.get("themes")),
                        "avancement": projet.get("avancement", "") or "",
                        "connectivite": [
                            conn_by_id[i]
                            for i in ref_ids(projet.get("connectivites"))
                            if conn_by_id.get(i)
                        ],
                        "echelle": projet.get("echelle", "") or "",
                        "description": projet.get("description", "") or "",
                        "cas_usages": cas_by_projet.get(pid, []),
                        "partenaires": part_by_projet.get(pid, []),
                        "programmes": prog_by_projet.get(pid, []),
                        "documents": doc_by_projet.get(pid, []),
                    }
                )

            coords = stored_coords(dict(c)) or geo_results.get(c["id"])
            result_collectivites.append(
                {
                    "id": c["id"],
                    "nom": str(c.get("nom") or ""),
                    "siren": c.get("siren", ""),
                    "statut": first_value(dict(c), "statut"),
                    "couverture": first_value(dict(c), "couverture"),
                    "dep": dep_by_id.get(c.get("departement") or 0, ""),
                    "num_dep": c.get("num_dep", "") or "",
                    "reg": c.get("region", "") or "",
                    "site_web": c.get("site_web", "") or "",
                    "adresse": c.get("adresse", "") or "",
                    "url_logo": c.get("url_logo", "") or "",
                    "lat": coords[0] if coords else None,
                    "lng": coords[1] if coords else None,
                    "nb_projets": len(c_projets),
                    "projets": c_projets,
                }
            )

        # Stats globales (projets dédupliqués)
        seen_ids: set[int] = set()
        unique_projets: list[dict] = []
        for c in result_collectivites:
            for p in c["projets"]:
                if p["id"] not in seen_ids:
                    seen_ids.add(p["id"])
                    unique_projets.append(p)

        par_connectivite: dict[str, int] = {}
        par_avancement: dict[str, int] = {}
        par_domaine: dict[str, int] = {}
        all_cas_usages: set[str] = set()
        for p in unique_projets:
            for conn in p["connectivite"]:
                par_connectivite[conn] = par_connectivite.get(conn, 0) + 1
            if p["avancement"]:
                par_avancement[p["avancement"]] = (
                    par_avancement.get(p["avancement"], 0) + 1
                )
            for dom in p["domaine"]:
                par_domaine[dom] = par_domaine.get(dom, 0) + 1
            for cu in p["cas_usages"]:
                if cu.get("nom"):
                    all_cas_usages.add(cu["nom"])

        filtres = {
            "couvertures": sorted(
                {c["couverture"] for c in result_collectivites if c["couverture"]}
            ),
            "statuts": sorted(
                {c["statut"] for c in result_collectivites if c["statut"]}
            ),
            "domaines": sorted(par_domaine.keys()),
            "connectivites": sorted(par_connectivite.keys()),
            "avancements": sorted(par_avancement.keys()),
            "cas_usages": sorted(all_cas_usages),
        }

        return {
            "collectivites": result_collectivites,
            "stats": {
                "nb_collectivites": len(result_collectivites),
                "nb_projets": len(unique_projets),
                "par_connectivite": par_connectivite,
                "par_avancement": par_avancement,
                "par_domaine": par_domaine,
                "nb_cas_usages": len(all_cas_usages),
            },
            "filtres": filtres,
        }

    async def _resolve_coords(
        self, collectivites: list[Any], dep_by_id: dict[int, str]
    ) -> dict[int, tuple[float, float] | None]:
        """Géocode UNIQUEMENT les collectivités sans coordonnées stockées."""
        a_geocoder = [c for c in collectivites if stored_coords(dict(c)) is None]
        if not a_geocoder:
            return {}
        resolver = GeoResolver(self._references.list_departements())
        semaphore = asyncio.Semaphore(_GEOCODE_PARALLELISME)
        results: dict[int, tuple[float, float] | None] = {}

        async def _geo(record: Any) -> None:
            fields = {
                "nom": record.get("nom"),
                "adresse": record.get("adresse"),
                "num_dep": record.get("num_dep"),
                # departement est une référence : on passe le NOM du département
                "dep": dep_by_id.get(record.get("departement") or 0, ""),
                "reg": record.get("region"),
            }
            async with semaphore:
                results[record["id"]] = await resolver.resolve(
                    fields, self._geocode.geocode
                )

        await asyncio.gather(*[_geo(c) for c in a_geocoder])
        return results
