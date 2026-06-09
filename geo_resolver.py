"""
Résolution géographique des collectivités → (lat, lng).

Beaucoup de collectivités n'ont ni adresse ni département renseignés, seulement
un nom (ex. « CA La Rochelle Agglo », « CR Ile-de-France », « SDE 22 »).
Géocoder ce nom brut sur une API d'ADRESSES renvoie une rue quelconque, souvent
dans la mauvaise région (« La Rochelle » → une rue dans la Manche, « Ile de
France » → une rue dans le Morbihan…).

Stratégie robuste :
  1. Déterminer le département/région *attendu* à partir du nom et des champs.
  2. Géocoder un nom de ville nettoyé en `type=municipality`.
  3. VALIDER le résultat contre le département attendu ; en cas d'échec ou de
     mauvais département, se rabattre sur les coordonnées de la préfecture du
     bon département (ou de la région). Ainsi un point ne tombe jamais dans la
     mauvaise région.
"""

import re
import unicodedata

from data_lists import DEPARTEMENTS

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

# --- Coordonnées des chefs-lieux de région (clés en forme normalisée) ---
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


def _norm(s: str) -> str:
    """Minuscule, sans accents, apostrophes/tirets normalisés, espaces compactés."""
    if not s:
        return ""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.lower().replace("’", " ").replace("'", " ").replace("-", " ")
    return re.sub(r"\s+", " ", s).strip()


# nom de département normalisé → numéro (depuis data_lists.DEPARTEMENTS)
DEP_NAME_TO_NUM: dict[str, str] = {}
for _entry in DEPARTEMENTS:
    _num, _name = _entry.split(" - ", 1)
    DEP_NAME_TO_NUM[_norm(_name)] = _num.strip()

# Acronymes / noms de syndicats sans indice géographique exploitable → département
ACRONYM_DEP: dict[str, str] = {
    "sddea": "10",      # Aube
    "sdef": "29",       # Finistère
    "serpn": "27",      # Eure
    "siea": "01",       # Ain
    "sieda": "12",      # Aveyron
    "sieds": "79",      # Deux-Sèvres
    "sieeen": "58",     # Nièvre
    "sieml": "49",      # Maine-et-Loire
    "sipperec": "75",   # Paris / petite couronne
    "syaden": "11",     # Aude
    "syane": "74",      # Haute-Savoie
    "sydesl": "71",     # Saône-et-Loire
    "sydev": "85",      # Vendée
    "useda": "02",      # Aisne
    "gip arnia": "25",  # Besançon (Doubs)
}

# Synonymes territoriaux (territoire historique) → département
SYNONYM_DEP: dict[str, str] = {
    "perigord": "24",       # Dordogne
    "berry": "18",          # Cher (Berry Numérique)
    "val de loire": "37",   # Indre-et-Loire (Val-de-Loire Numérique)
}

# Régions : clés normalisées → coordonnées (forme normalisée pour comparaisons)
REGION_COORDS: dict[str, tuple[float, float]] = {
    _norm(k): v for k, v in _REGION_COORDS_RAW.items()
}
_REGION_KEYS = sorted(REGION_COORDS.keys(), key=len, reverse=True)
# Noms de départements triés par longueur décroissante (match « Haute-Garonne » avant « Garonne »)
_DEP_NAME_KEYS = sorted(DEP_NAME_TO_NUM.keys(), key=len, reverse=True)

# Overrides manuels (nom normalisé → coordonnées) pour les cas non résolvables
# automatiquement (acronymes opaques, EPCI dont le siège n'est pas le nom).
# Valeur None = ne pas placer plutôt que placer au mauvais endroit.
MANUAL_COORDS: dict[str, tuple[float, float] | None] = {
    "ca pays ajaccien": (41.9337, 8.7153),          # Ajaccio (Corse-du-Sud)
    "ca caux seine agglo": (49.5193, 0.5388),        # Lillebonne (Seine-Maritime)
    "cc du pays haut val d alzette": (49.4646, 5.9889),  # Audun-le-Tiche (Moselle)
    "ept grand paris seine ouest": (48.8352, 2.2399),    # Boulogne-Billancourt (Hauts-de-Seine)
    "gip adine": None,                               # localisation incertaine → non placé
}

# Tokens administratifs retirés en tête de nom (forme normalisée, sans accent)
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
# Mots qualificatifs : on coupe le nom juste avant (la ville est ce qui précède)
_QUALIFIERS = {
    "metropole", "metropoles", "agglomeration", "agglo", "agglopole",
    "communaute", "provence", "mediterranee", "cote", "bretagne", "seine",
    "loire", "val", "occidentale", "europeenne", "alpes", "plus", "energies",
    "energie", "numerique", "grand",
}
# Mots-clés de syndicat/EPCI retirés pour isoler le « cœur territorial ».
# On NE retire PAS les connecteurs (de/d/…) car ils font partie de noms de
# départements (« Val-d'Oise », « Côtes-d'Armor »…).
_CORE_NOISE = _ADMIN_LEAD | {
    "numerique", "energies", "energie", "agglo", "agglomeration", "agglopole",
    "metropole", "mediterranee",
}
# Sous-mots « forts » : coupent la ville même au sein d'un token composé
# (« Nice Côte-d'Azur » → « Nice »), mais seulement après une 1re ville retenue.
_STRONG_QUALIFIERS = {
    "cote", "provence", "mediterranee", "seine", "loire", "bretagne", "azur",
    "alpes",
}


def expected_dep(nom: str, num_dep: str = "", dep: str = "", reg: str = "") -> str | None:
    """Détermine, prudemment, le code département attendu pour une collectivité."""
    # 1. Champ num_dep explicite
    nd = (num_dep or "").strip().upper()
    if nd:
        m = re.match(r"^(2A|2B|\d{1,3})", nd)
        if m:
            code = m.group(1)
            if code.isdigit() and len(code) < 2:
                code = code.zfill(2)
            if code in DEP_PREF_COORDS:
                return code

    norm = _norm(nom)

    # 2. Acronyme connu
    if norm in ACRONYM_DEP:
        return ACRONYM_DEP[norm]

    # 3. Synonyme territorial explicite (Périgord, Berry, Val-de-Loire…)
    for key, code in SYNONYM_DEP.items():
        if re.search(r"\b" + re.escape(key) + r"\b", norm):
            return code

    # 4. Numéro de département présent dans le nom (ex. « SDE 22 », « 59/62 »)
    for tok in re.findall(r"\b(2A|2B|\d{2,3})\b", norm.upper()):
        if tok in DEP_PREF_COORDS:
            return tok

    # 5. « Cœur territorial » = un nom de département (ex. « CD Hérault »,
    #    « Gironde Numérique », « Val-d'Oise Numérique »). On retire les mots de
    #    syndicat/EPCI (mais pas les connecteurs) et on exige une égalité stricte
    #    → pas de faux positif type « Angers Loire ».
    core = " ".join(w for w in norm.split() if w not in _CORE_NOISE).strip()
    if core in DEP_NAME_TO_NUM:
        return DEP_NAME_TO_NUM[core]

    # 6. Nom de département en suffixe précédé d'un connecteur
    #    (ex. « Saint-Quentin-en-Yvelines » → Yvelines).
    for key in _DEP_NAME_KEYS:
        if re.search(r"\b(en|de|du|d)\s+" + re.escape(key) + r"$", norm):
            return DEP_NAME_TO_NUM[key]

    # 6. Champ dep texte
    nd_txt = _norm(dep)
    if nd_txt in DEP_NAME_TO_NUM:
        return DEP_NAME_TO_NUM[nd_txt]

    return None


def _is_region_entity(norm: str) -> bool:
    """Vrai si le nom désigne une région (Conseil régional…)."""
    return bool(re.match(r"^(cr|region|conseil regional)\b", norm))


def region_coords(nom: str, reg: str = "") -> tuple[float, float] | None:
    """Coordonnées du chef-lieu de région si une région est identifiée."""
    for src in (reg, nom):
        norm = _norm(src)
        if not norm:
            continue
        if norm in REGION_COORDS:
            return REGION_COORDS[norm]
        for key in _REGION_KEYS:
            if re.search(r"\b" + re.escape(key) + r"\b", norm):
                return REGION_COORDS[key]
    return None


def _is_qualifier_token(tok: str) -> bool:
    """Vrai si le token (mot entier) est un qualificatif marquant la fin de la ville."""
    return _norm(tok) in _QUALIFIERS


def city_query(nom: str) -> str | None:
    """Extrait un nom de ville géocodable à partir du nom de la collectivité."""
    if not nom or not nom.strip():
        return None
    tokens = nom.split()
    norms = [_norm(t) for t in tokens]

    # Phase A : retirer les tokens administratifs de tête + connecteurs qui suivent
    i = 0
    while i < len(tokens) and norms[i] in _ADMIN_LEAD:
        i += 1
        while i < len(tokens) and norms[i] in _CONNECTORS:
            i += 1

    # Phase B : accumuler jusqu'au premier qualificatif
    kept: list[str] = []
    for tok in tokens[i:]:
        ntok = _norm(tok)
        if ntok in _QUALIFIERS:  # token entier qualificatif → stop
            break
        # sous-mot fort (Côte-d'Azur, Seine…) → stop, mais seulement si on a
        # déjà retenu une ville (sinon « Aix-Marseille-Provence » serait perdu)
        if kept and any(w in _STRONG_QUALIFIERS for w in ntok.split()):
            break
        kept.append(tok)

    city = " ".join(kept).strip(" -,")
    if not city:
        return None
    # Si la « ville » est en fait un nom de département (« CD Hérault »,
    # « Gironde Numérique »), on laisse la voie « préfecture du département »
    # (placement plus pertinent). Exception : Paris, à la fois commune et dépt.
    ncity = _norm(city)
    if ncity in DEP_NAME_TO_NUM and ncity != "paris":
        return None
    return city


async def resolve(fields: dict, geocode_fn) -> tuple[float, float] | None:
    """
    Résout les coordonnées d'une collectivité.

    `geocode_fn(query, expected_dep=None, municipality=False)` doit renvoyer
    (lat, lng) — en validant contre `expected_dep` si fourni — ou None.
    """
    nom = (fields.get("nom") or "").strip()
    adresse = (fields.get("adresse") or "").strip()
    num_dep = (fields.get("num_dep") or "").strip()
    dep = (fields.get("dep") or "").strip()
    reg = (fields.get("reg") or "").strip()
    norm = _norm(nom)

    # 0. Override manuel explicite (peut forcer None pour ne pas mal placer)
    if norm in MANUAL_COORDS:
        return MANUAL_COORDS[norm]

    exp = expected_dep(nom, num_dep, dep, reg)

    # 1. Adresse postale (la plus précise) — validée si on connaît le département
    if adresse:
        coords = await geocode_fn(adresse, expected_dep=exp)
        if coords:
            return coords

    # 2. Entité régionale (Conseil régional…) → chef-lieu de région
    if exp is None and _is_region_entity(norm):
        rc = region_coords(nom, reg)
        if rc:
            return rc

    # 3. Ville nettoyée, géocodée comme commune et validée
    city = city_query(nom)
    if city:
        coords = await geocode_fn(city, expected_dep=exp, municipality=True)
        if coords:
            return coords

    # 4. Repli : préfecture du département attendu
    if exp and exp in DEP_PREF_COORDS:
        return DEP_PREF_COORDS[exp]

    # 5. Repli : chef-lieu de région
    rc = region_coords(nom, reg)
    if rc:
        return rc

    return None
