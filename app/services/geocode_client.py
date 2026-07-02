"""Client api-adresse.data.gouv.fr : géocodage borné et validé.

- timeout 10 s, échec de géocodage ≠ échec de page (faiblesse v1 n°10) ;
- validation départementale : un résultat hors du département attendu est
  rejeté (le repli préfecture est géré par le GeoResolver appelant) ;
- cache mémoire des résultats (les échecs transitoires ne sont PAS cachés).
"""

import logging

import httpx

logger = logging.getLogger(__name__)

_API_URL = "https://api-adresse.data.gouv.fr/search/"


def stored_coords(fields: dict) -> tuple[float, float] | None:
    """Coordonnées stockées dans Grist (latitude/longitude), ou None si absentes/invalides."""
    try:
        lat = float(str(fields.get("latitude") or "").replace(",", "."))
        lng = float(str(fields.get("longitude") or "").replace(",", "."))
        if lat or lng:
            return (lat, lng)
    except (ValueError, TypeError):
        pass
    return None


def _feature_dep(props: dict) -> str:
    """Code département d'un résultat api-adresse (context ou citycode)."""
    ctx = props.get("context") or ""
    if ctx:
        first = ctx.split(",")[0].strip()
        if first:
            return first
    citycode = props.get("citycode") or ""
    if citycode[:2] in ("2A", "2B"):
        return citycode[:2]
    return citycode[:3] if citycode[:2] == "97" else citycode[:2]


class GeocodeClient:
    def __init__(self, timeout_seconds: float = 10.0):
        self._timeout = timeout_seconds
        self._cache: dict[str, tuple[float, float] | None] = {}

    async def geocode(
        self,
        query: str,
        expected_dep: str | None = None,
        municipality: bool = False,
    ) -> tuple[float, float] | None:
        """Géocode une requête. Retourne (lat, lng) ou None.

        - ``municipality=True`` restreint aux communes (type=municipality) ;
        - ``expected_dep`` : seul un résultat de ce département est retenu.
        """
        if not query or not query.strip():
            return None
        query = query.strip()
        cache_key = f"{query}|{expected_dep or ''}|{int(municipality)}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        result: tuple[float, float] | None = None
        try:
            params: dict = {"q": query, "limit": 8}
            if municipality:
                params["type"] = "municipality"
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(_API_URL, params=params)
                resp.raise_for_status()
                features = resp.json().get("features", [])
        except (httpx.HTTPError, ValueError) as exc:
            # Échec transitoire (rate-limit, réseau…) : non caché
            logger.warning("Géocodage échoué pour '%s' : %s", query,
                           type(exc).__name__)
            return None
        if features:
            if expected_dep:
                for feat in features:
                    if _feature_dep(feat.get("properties", {})) == expected_dep:
                        coords = feat["geometry"]["coordinates"]
                        result = (coords[1], coords[0])
                        break
            else:
                coords = features[0]["geometry"]["coordinates"]
                result = (coords[1], coords[0])
        self._cache[cache_key] = result
        return result
