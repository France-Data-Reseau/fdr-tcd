"""Résolution géographique des collectivités → (lat, lng).

Héritier du ``geo_resolver`` v1 (mêmes heuristiques de nettoyage de nom), mais
toutes les données de référence sont injectées depuis Grist : la correspondance
nom de département → numéro et les coordonnées (préfectures, chefs-lieux) sont
lues depuis ``BDD_Departements`` et ``BDD_Regions``. Les coordonnées d'une
collectivité vivent sur SA fiche (``BDD_Collectivites``) — aucun override en dur.

Stratégie (héritée de la v1, éprouvée) :
1. déterminer le département/région ATTENDU à partir du nom et des champs ;
2. géocoder un nom de ville nettoyé en ``type=municipality`` ;
3. VALIDER le résultat contre le département attendu ; en cas d'échec, se
   rabattre sur la préfecture du bon département (ou le chef-lieu de région)
   — un point ne tombe jamais dans la mauvaise région.
"""

import re
import unicodedata
from collections.abc import Awaitable, Callable

from app.repositories.types import DepartementRecord, RegionRecord

GeocodeFn = Callable[..., Awaitable[tuple[float, float] | None]]

# ============================================================================
# DONNÉES DE RÉFÉRENCE — MAINTENUES DANS GRIST (``BDD_Departements`` avec
# latitude/longitude, et ``BDD_Regions``). Les constantes ci-dessous ne servent
# plus que de REPLI de sécurité si ces sources Grist sont absentes/vides. En
# fonctionnement normal, ``GeoResolver`` lit Grist. Pour corriger le placement
# d'une collectivité, éditer SA fiche (``BDD_Collectivites`` : latitude/longitude
# ou le champ département) — pas ce fichier.
# ============================================================================

# --- Coordonnées des préfectures (1 point fiable par département) ---
DEP_PREF_COORDS: dict[str, tuple[float, float]] = {
    "01": (46.2066, 5.242), "02": (49.5703, 3.6147), "03": (46.5595, 3.3278),
    "04": (44.0893, 6.2427), "05": (44.5632, 6.0768), "06": (43.7127, 7.2509),
    "07": (44.726, 4.5949), "08": (49.7676, 4.7173), "09": (42.9688, 1.6074),
    "10": (48.2928, 4.0751), "11": (43.2068, 2.3494), "12": (44.3593, 2.5667),
    "13": (43.282, 5.405), "14": (49.1843, -0.3719), "15": (44.9188, 2.4351),
    "16": (45.6441, 0.148), "17": (46.1575, -1.1706), "18": (47.0829, 2.4023),
    "19": (45.2672, 1.7641), "2A": (41.9337, 8.7153), "2B": (42.6876, 9.4352),
    "21": (47.332, 5.0336), "22": (48.5082, -2.7661), "23": (46.1718, 1.875),
    "24": (45.1931, 0.7113), "25": (47.2519, 6.0017), "26": (44.9209, 4.923),
    "27": (49.0206, 1.1469), "28": (48.4465, 1.5023), "29": (47.9987, -4.0932),
    "30": (43.8147, 4.3563), "31": (43.6041, 1.4338), "32": (43.657, 0.5708),
    "33": (44.8519, -0.5879), "34": (43.6105, 3.8705), "35": (48.1109, -1.6837),
    "36": (46.8044, 1.693), "37": (47.3955, 0.6958), "38": (45.1828, 5.7243),
    "39": (46.6775, 5.5599), "40": (43.8914, -0.5002), "41": (47.5814, 1.3165),
    "42": (45.4302, 4.37), "43": (45.0318, 3.8997), "44": (47.2394, -1.5553),
    "45": (47.8736, 1.9114), "46": (44.4576, 1.4383), "47": (44.2023, 0.631),
    "48": (44.5264, 3.484), "49": (47.4675, -0.5616), "50": (49.1138, -1.0802),
    "51": (48.9553, 4.3683), "52": (48.1043, 5.13), "53": (48.0596, -0.7716),
    "54": (48.6881, 6.1713), "55": (48.7739, 5.165), "56": (47.66, -2.7522),
    "57": (49.1084, 6.1949), "58": (46.9885, 3.1608), "59": (50.631, 3.0454),
    "60": (49.4393, 2.0879), "61": (48.4296, 0.092), "62": (50.2879, 2.7683),
    "63": (45.7867, 3.1071), "64": (43.3135, -0.3431), "65": (43.2393, 0.064),
    "66": (42.7015, 2.9028), "67": (48.5798, 7.7615), "68": (48.0818, 7.3526),
    "69": (45.758, 4.835), "70": (47.6287, 6.158), "71": (46.3259, 4.811),
    "72": (47.9934, 0.1912), "73": (45.5832, 5.9093), "74": (45.9016, 6.1253),
    "75": (48.859, 2.347), "76": (49.4401, 1.0939), "77": (48.5413, 2.6557),
    "78": (48.8029, 2.1211), "79": (46.3272, -0.4663), "80": (49.903, 2.2926),
    "81": (43.9304, 2.1363), "82": (44.0198, 1.3638), "83": (43.1367, 5.9338),
    "84": (43.9363, 4.8489), "85": (46.6708, -1.4125), "86": (46.5866, 0.3567),
    "87": (45.8562, 1.2213), "88": (48.1702, 6.4849), "89": (47.7902, 3.5803),
    "90": (47.6409, 6.8575), "91": (48.6273, 2.4327), "92": (48.8981, 2.2023),
    "93": (48.9074, 2.4433), "94": (48.7845, 2.453), "95": (49.0476, 2.1),
    "971": (15.9986, -61.7295), "972": (14.6364, -61.0641), "973": (4.9252, -52.3116),
    "974": (-20.9098, 55.4446), "976": (-12.7977, 45.1976),
}

# --- Coordonnées des chefs-lieux de région ---
_REGION_COORDS_RAW: dict[str, tuple[float, float]] = {
    "Auvergne-Rhône-Alpes": (45.758, 4.835),        # Lyon
    "Bourgogne-Franche-Comté": (47.332, 5.0336),    # Dijon
    "Bretagne": (48.1109, -1.6837),                 # Rennes
    "Centre-Val de Loire": (47.8736, 1.9114),       # Orléans
    "Corse": (41.9337, 8.7153),                     # Ajaccio
    "Grand Est": (48.5798, 7.7615),                 # Strasbourg
    "Hauts-de-France": (50.631, 3.0454),            # Lille
    "Île-de-France": (48.859, 2.347),               # Paris
    "Normandie": (49.4401, 1.0939),                 # Rouen
    "Nouvelle-Aquitaine": (44.8519, -0.5879),       # Bordeaux
    "Occitanie": (43.6041, 1.4338),                 # Toulouse
    "Pays de la Loire": (47.2394, -1.5553),         # Nantes
    "Provence-Alpes-Côte d'Azur": (43.282, 5.405),  # Marseille
    "Guadeloupe": (15.9986, -61.7295),
    "Martinique": (14.6364, -61.0641),
    "Guyane": (4.9252, -52.3116),
    "La Réunion": (-20.9098, 55.4446),
    "Mayotte": (-12.7977, 45.1976),
}

# Tokens administratifs retirés en tête de nom
_ADMIN_LEAD = {
    "ca", "cc", "cu", "cd", "cr", "ct", "ept", "gip", "sivu", "sivom",
    "metropole", "communaute", "ville", "pole", "syndicat", "grand", "pays",
    "bassin",
}
# Connecteurs retirés uniquement à la suite d'un token administratif
_CONNECTORS = {
    "de", "du", "des", "d", "la", "le", "les", "l", "a",
    "agglomeration", "communes", "urbaine", "europeenne", "metropolitain",
}
# Mots qualificatifs : on coupe le nom juste avant
_QUALIFIERS = {
    "metropole", "metropoles", "agglomeration", "agglo", "agglopole",
    "communaute", "provence", "mediterranee", "cote", "bretagne", "seine",
    "loire", "val", "occidentale", "europeenne", "alpes", "plus", "energies",
    "energie", "numerique", "grand",
}
# Mots-clés de syndicat/EPCI retirés pour isoler le « cœur territorial »
_CORE_NOISE = _ADMIN_LEAD | {
    "numerique", "energies", "energie", "agglo", "agglomeration", "agglopole",
    "metropole", "mediterranee",
}
# Sous-mots « forts » : coupent la ville au sein d'un token composé
_STRONG_QUALIFIERS = {
    "cote", "provence", "mediterranee", "seine", "loire", "bretagne", "azur",
    "alpes",
}


def _norm(s: str) -> str:
    """Minuscule, sans accents, apostrophes/tirets normalisés, espaces compactés."""
    if not s:
        return ""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.lower().replace("’", " ").replace("'", " ").replace("-", " ")
    return re.sub(r"\s+", " ", s).strip()


REGION_COORDS: dict[str, tuple[float, float]] = {
    _norm(k): v for k, v in _REGION_COORDS_RAW.items()
}
_REGION_KEYS = sorted(REGION_COORDS.keys(), key=len, reverse=True)


class GeoResolver:
    """Résolveur géographique.

    Toutes les données de référence sont **injectées depuis Grist** (maintenables
    par un admin sans redéploiement) :

    - ``departements`` (``BDD_Departements``) : nom → numéro, et
      ``latitude``/``longitude`` → coordonnées des préfectures (repli) ;
    - ``regions`` (``BDD_Regions``) : chefs-lieux de région (repli).

    Si une source est absente ou vide, on retombe sur les constantes en dur
    définies plus haut (mêmes valeurs) — l'app ne casse jamais. Les coordonnées
    d'une collectivité sont lues en priorité sur SA fiche (hors de cette classe,
    via ``stored_coords``) ; ce résolveur n'intervient qu'à défaut.
    """

    def __init__(
        self,
        departements: list[DepartementRecord],
        regions: list[RegionRecord] | None = None,
    ):
        # nom de département normalisé → numéro ; numéro → coord. préfecture
        self._dep_name_to_num: dict[str, str] = {}
        self._dep_pref_coords: dict[str, tuple[float, float]] = {}
        for d in departements:
            nom = str(d.get("nom") or "")
            num = str(d.get("num_dep") or "").strip()
            if nom and num:
                self._dep_name_to_num[_norm(nom)] = num
            lat, lng = d.get("latitude"), d.get("longitude")
            if num and lat is not None and lng is not None:
                self._dep_pref_coords[num] = (float(lat), float(lng))
        if not self._dep_pref_coords:  # repli : coordonnées en dur
            self._dep_pref_coords = DEP_PREF_COORDS
        # « Haute-Garonne » doit matcher avant « Garonne »
        self._dep_name_keys = sorted(
            self._dep_name_to_num.keys(), key=len, reverse=True
        )

        # Chefs-lieux de région (repli : _REGION_COORDS_RAW via REGION_COORDS)
        region_coords: dict[str, tuple[float, float]] = {}
        for r in regions or []:
            nom = str(r.get("nom") or "")
            lat, lng = r.get("latitude"), r.get("longitude")
            if nom and lat is not None and lng is not None:
                region_coords[_norm(nom)] = (float(lat), float(lng))
        self._region_coords = region_coords or REGION_COORDS
        self._region_keys = sorted(self._region_coords.keys(), key=len, reverse=True)

    # --- Département attendu ---

    def expected_dep(
        self, nom: str, num_dep: str = "", dep: str = "", reg: str = ""
    ) -> str | None:
        """Détermine, prudemment, le code département attendu."""
        # 1. Champ num_dep explicite
        nd = (num_dep or "").strip().upper()
        if nd:
            m = re.match(r"^(2A|2B|\d{1,3})", nd)
            if m:
                code = m.group(1)
                if code.isdigit() and len(code) < 2:
                    code = code.zfill(2)
                if code in self._dep_pref_coords:
                    return code

        norm = _norm(nom)

        # 2. Numéro de département présent dans le nom (« SDE 22 »…)
        for tok in re.findall(r"\b(2A|2B|\d{2,3})\b", norm.upper()):
            if tok in self._dep_pref_coords:
                return tok

        # 3. « Cœur territorial » = un nom de département (« CD Hérault »…)
        core = " ".join(w for w in norm.split() if w not in _CORE_NOISE).strip()
        if core in self._dep_name_to_num:
            return self._dep_name_to_num[core]

        # 4. Nom de département en suffixe précédé d'un connecteur
        for key in self._dep_name_keys:
            if re.search(r"\b(en|de|du|d)\s+" + re.escape(key) + r"$", norm):
                return self._dep_name_to_num[key]

        # 5. Champ dep texte
        nd_txt = _norm(dep)
        if nd_txt in self._dep_name_to_num:
            return self._dep_name_to_num[nd_txt]

        return None

    # --- Helpers ---

    @staticmethod
    def _is_region_entity(norm: str) -> bool:
        return bool(re.match(r"^(cr|region|conseil regional)\b", norm))

    def region_coords(self, nom: str, reg: str = "") -> tuple[float, float] | None:
        """Coordonnées du chef-lieu de région si une région est identifiée."""
        for src in (reg, nom):
            norm = _norm(src)
            if not norm:
                continue
            if norm in self._region_coords:
                return self._region_coords[norm]
            for key in self._region_keys:
                if re.search(r"\b" + re.escape(key) + r"\b", norm):
                    return self._region_coords[key]
        return None

    def city_query(self, nom: str) -> str | None:
        """Extrait un nom de ville géocodable du nom de la collectivité."""
        if not nom or not nom.strip():
            return None
        tokens = nom.split()
        norms = [_norm(t) for t in tokens]

        # Phase A : retirer les tokens administratifs de tête + connecteurs
        i = 0
        while i < len(tokens) and norms[i] in _ADMIN_LEAD:
            i += 1
            while i < len(tokens) and norms[i] in _CONNECTORS:
                i += 1

        # Phase B : accumuler jusqu'au premier qualificatif
        kept: list[str] = []
        for tok in tokens[i:]:
            ntok = _norm(tok)
            if ntok in _QUALIFIERS:
                break
            if kept and any(w in _STRONG_QUALIFIERS for w in ntok.split()):
                break
            kept.append(tok)

        city = " ".join(kept).strip(" -,")
        if not city:
            return None
        # Si la « ville » est un nom de département, laisser la voie
        # « préfecture » (exception : Paris, commune ET département)
        ncity = _norm(city)
        if ncity in self._dep_name_to_num and ncity != "paris":
            return None
        return city

    # --- Résolution complète ---

    async def resolve(
        self, fields: dict, geocode_fn: GeocodeFn
    ) -> tuple[float, float] | None:
        """Résout les coordonnées d'une collectivité.

        ``geocode_fn(query, expected_dep=None, municipality=False)`` renvoie
        (lat, lng) — validé contre ``expected_dep`` si fourni — ou None.
        ``fields`` : nom, adresse, num_dep, dep (NOM du département), reg.
        """
        nom = str(fields.get("nom") or "").strip()
        adresse = str(fields.get("adresse") or "").strip()
        num_dep = str(fields.get("num_dep") or "").strip()
        dep = str(fields.get("dep") or "").strip()
        reg = str(fields.get("reg") or "").strip()
        norm = _norm(nom)

        exp = self.expected_dep(nom, num_dep, dep, reg)

        # 1. Adresse postale (la plus précise) — validée si département connu
        if adresse:
            coords = await geocode_fn(adresse, expected_dep=exp)
            if coords:
                return coords

        # 2. Entité régionale (Conseil régional…) → chef-lieu de région
        if exp is None and self._is_region_entity(norm):
            rc = self.region_coords(nom, reg)
            if rc:
                return rc

        # 3. Ville nettoyée, géocodée comme commune et validée
        city = self.city_query(nom)
        if city:
            coords = await geocode_fn(city, expected_dep=exp, municipality=True)
            if coords:
                return coords

        # 4. Repli : préfecture du département attendu
        if exp and exp in self._dep_pref_coords:
            return self._dep_pref_coords[exp]

        # 5. Repli : chef-lieu de région
        return self.region_coords(nom, reg)
