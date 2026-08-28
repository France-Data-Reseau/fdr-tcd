# 11. Données géographiques « en dur » — audit et recommandation

> Réponse à la demande : sortir du code les données codées en dur (surtout le
> géocodage), pour rendre l'application **maintenable facilement** (éditable sans
> redéploiement). Fichier concerné : `app/services/geo_service.py`.
> Date : 2026-08-27.

---

## 1. Ce qui est DÉJÀ propre

La liste des **départements** (nom → numéro) n'est **plus** en dur : elle est lue
depuis **`BDD_Departements`** (Grist). C'est le bon modèle à généraliser.

## 2. Inventaire des données encore en dur dans `geo_service.py`

| Bloc | Volume | Rôle | Change souvent ? |
|---|---|---|---|
| `DEP_PREF_COORDS` | ~101 | Coordonnées (lat, lng) de la **préfecture** de chaque département (repli quand le géocodage échoue) | Non (stable) |
| `_REGION_COORDS_RAW` | ~18 | Coordonnées des **chefs-lieux de région** (repli régional) | Non (stable) |
| `ACRONYM_DEP` | ~15 | **Acronymes de syndicats** sans indice géographique → département (`sddea`→10…) | **Oui** (s'enrichit à chaque nouvelle collectivité mal géocodée) |
| `SYNONYM_DEP` | ~3 | **Synonymes territoriaux** → département (`perigord`→24…) | **Oui** |
| `MANUAL_COORDS` | ~5 | **Overrides manuels** (nom → coordonnées, ou « ne pas placer ») pour les cas non résolvables | **Oui** |
| `_ADMIN_LEAD`, `_CONNECTORS`, `_QUALIFIERS`, `_CORE_NOISE`, `_STRONG_QUALIFIERS` | ~80 tokens | Heuristiques de **nettoyage de noms** (extraire la ville d'un nom de collectivité) | Non (technique) |

## 3. Recommandation — quoi migrer, quoi garder

Le critère : **migrer vers Grist ce qui relève du métier et s'enrichit** ; garder
en dur ce qui est **technique et stable**.

### 🟢 Priorité 1 — À migrer vers Grist (fort gain de maintenabilité)
**`ACRONYM_DEP` + `SYNONYM_DEP` + `MANUAL_COORDS`** : ce sont des **règles métier
correctives** qui grossissent à chaque nouvelle collectivité mal placée.
Aujourd'hui, corriger un point sur la carte = modifier le code + redéployer. À
terme, un admin devrait pouvoir le faire **dans Grist**.

→ **Proposition : une table `BDD_GeoCorrections`** :
| colonne | type | rôle |
|---|---|---|
| `nom_normalise` | Text | nom de la collectivité normalisé (clé) |
| `departement` | Ref:BDD_Departements | forcer un département (cas acronyme/synonyme) |
| `latitude`, `longitude` | Num | forcer des coordonnées précises (override) |
| `ne_pas_placer` | Bool | cas « localisation incertaine, ne pas afficher » |

### 🟡 Priorité 2 — À rapatrier dans les tables de référence existantes
- **`DEP_PREF_COORDS`** → ajouter **`latitude` / `longitude`** à **`BDD_Departements`**
  (coordonnées de la préfecture). Centralise toute l'info département au même endroit.
- **`_REGION_COORDS_RAW`** → une petite table **`BDD_Regions`** (`nom`, `latitude`,
  `longitude`), qui pourrait aussi servir de référentiel propre des régions
  (aujourd'hui les régions ne sont qu'une valeur de choix).

### ⚪ À garder en dur (aucun gain à migrer)
Les listes de **nettoyage de noms** (`_ADMIN_LEAD`, `_CONNECTORS`, `_QUALIFIERS`…)
sont des **heuristiques techniques** de parsing, pas des données métier. Les
mettre en base compliquerait le code pour un bénéfice nul. Elles restent dans le
code (documentées).

## 4. Comment ça marcherait (principe)

Comme pour `BDD_Departements` aujourd'hui : au démarrage / via le cache TTL, le
`GeoResolver` **charge ces tables de référence** (injectées par la couche
repository) au lieu de constantes Python. Zéro changement d'algorithme — on
remplace juste la **source** des données.

## 5. Effort estimé & séquencement proposé

1. **`BDD_GeoCorrections`** (priorité 1) — le plus rentable : création table Grist
   + lecture dans `GeoResolver` + reprise des ~23 entrées actuelles.
2. **`latitude`/`longitude` sur `BDD_Departements`** (priorité 2) — reprise des
   ~101 préfectures.
3. **`BDD_Regions`** (priorité 2) — reprise des ~18 régions.

Chaque étape est indépendante et testable ; à faire **après** la mise en prod de
la version SSO (ne pas mélanger les chantiers). À valider avec Victor avant
implémentation.

## 6. Lien open data

Ces tables de référence (`BDD_Departements` enrichi, `BDD_Regions`,
`BDD_GeoCorrections`) sont **non sensibles** et propres → parfaitement
diffusables dans une optique open data, contrairement aux `BDD_Utilisateurs` /
`BDD_Contacts` (données personnelles).
