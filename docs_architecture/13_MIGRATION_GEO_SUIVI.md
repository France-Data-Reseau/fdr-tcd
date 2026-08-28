# 13. Migration des données géo vers Grist — SUIVI D'EXÉCUTION

> Fichier de suivi de l'**étape 3** (audit : `docs_architecture/11`). Conçu pour
> **reprendre le chantier même après un résumé de contexte** : cocher au fur et à
> mesure, tout l'état nécessaire est ici.
>
> Contexte : le code applicatif à modifier est celui du dev FDR, déployé dans
> `~/stack/fdr-tcd-dev` sur le VPS (source de vérité vivante). Modif =
> éditer + `docker compose build fdr-tcd && up -d fdr-tcd`. Le Grist ciblé est la
> prod renommée (doc `<GRIST_DOC_ID>`).

> ## ✅ ÉTAPE 3 TERMINÉE ET VÉRIFIÉE (2026-08-28)
> Données géo migrées vers Grist + code adapté + déployé + testé (Grist 11/11,
> repli 17/17). Détail des phases plus bas.

---

## Objectif
Sortir de `app/services/geo_service.py` les données **éditables** → Grist, pour
qu'un admin puisse les corriger **sans redéploiement**. Les heuristiques
techniques de parsing (`_ADMIN_LEAD`, `_CONNECTORS`, `_QUALIFIERS`,
`_CORE_NOISE`, `_STRONG_QUALIFIERS`) **restent en dur**.

## Décisions de structure (état FINAL après revue du 2026-08-28)
| Structure Grist | Remplace (en dur) | Colonnes |
|---|---|---|
| **`BDD_Departements`** + 2 colonnes | `DEP_PREF_COORDS` (101) | `latitude` (Num), `longitude` (Num) — repli préfecture |
| **Table `BDD_Regions`** | `_REGION_COORDS_RAW` (18) | `nom` (Text), `latitude` (Num), `longitude` (Num) — repli chef-lieu |

> ⚠️ **`BDD_GeoCorrections` a d'abord été créée puis SUPPRIMÉE** après revue
> (journal 2026-08-28). Elle mélangeait 3 natures (acronyme→dép, coordonnées
> forcées, exclusion) avec des noms normalisés illisibles, ET était **redondante**
> : 22/23 collectivités concernées avaient déjà leurs coordonnées sur leur fiche
> `BDD_Collectivites` (lues **en priorité**), donc le géocodeur ne tournait jamais
> pour elles. **Design retenu : les corrections vivent sur la fiche de la
> collectivité** — `latitude`/`longitude` si connues, sinon le champ `departement`
> (→ repli préfecture automatique). Le mécanisme acronymes/synonymes/overrides a
> été **retiré du code** (`geo_service.py`, `reference_repository.py`,
> `restitution_service.py`, `types.py`, `test_geo_service.py`). Cas résiduel
> GIP ADINE = Agence Départementale (Aveyron) : rattachée à l'Aveyron +
> coordonnées de Rodez sur sa fiche. Résultat : **258/258 collectivités placées**.

## CHECKLIST

### Phase A — Grist (via script API)  ✅ FAIT (2026-08-28)
- [x] `BDD_GeoCorrections` créée + **23 corrections** (15 acronymes + 3 synonymes + 5 overrides).
- [x] `BDD_Departements` + `latitude`/`longitude` — **101 départements géolocalisés**.
- [x] `BDD_Regions` créée + **18 régions**.

### Phase B — Code (`~/stack/fdr-tcd-dev`)  ✅ FAIT (2026-08-28)
- [x] `app/repositories/types.py` : `DepartementRecord` + `latitude`/`longitude` ;
      nouveaux `GeoCorrectionRecord`, `RegionRecord` ; constantes
      `TABLE_GEO_CORRECTIONS`, `TABLE_REGIONS`.
- [x] `app/repositories/reference_repository.py` : `list_geo_corrections()` +
      `list_regions()` (dégradation douce → `[]` si table absente).
- [x] `app/services/geo_service.py` : `GeoResolver(departements, corrections,
      regions)` lit Grist ; **repli automatique sur les constantes** si une source
      est vide (l'app ne casse jamais). Constantes conservées comme repli + amorce
      (bloc d'en-tête commenté « éditer GRIST, pas ce fichier »).
- [x] `app/services/restitution_service.py` : passe corrections + régions au resolver.
- [x] `app/dependencies.py` : **rien à changer** (RestitutionService tient déjà le
      reference_repository).

### Phase C — Déploiement + test  ✅ FAIT (2026-08-28)
- [x] `docker compose build fdr-tcd && up -d fdr-tcd` — conteneur **healthy**,
      aucune erreur au boot (build offline, layer wheels cachée).
- [x] Vérif chemin **Grist** (données réelles) : **11/11 OK** — acronymes,
      synonymes, numéro dans le nom, repli préfecture, chef-lieu de région,
      override manuel, `ne_pas_placer`, dep par nom.
- [x] Vérif chemin **repli** (reproduit `tests/unit/test_geo_service.py`, car
      pytest absent de l'image runtime) : **17/17 OK**.

## Source des données (amorce + repli)
Constantes conservées dans `app/services/geo_service.py` : `DEP_PREF_COORDS`,
`_REGION_COORDS_RAW`, `ACRONYM_DEP`, `SYNONYM_DEP`, `MANUAL_COORDS`. Elles ont
servi à remplir Grist et restent en **repli de sécurité**. `test_geo_service.py`
importe encore `DEP_PREF_COORDS` → à conserver.

## Reste à faire (hors étape 3)
- **Reporter ces modifs dans la base à pousser** au moment de l'**étape 2** : la
  source de vérité complète et vivante est désormais le VPS `~/stack/fdr-tcd-dev`
  (code dev + finitions SSO + renommage URLs + étape 3). `C:\Users\vwels\fdr-tcd-src`
  est une base antérieure à resynchroniser depuis le VPS avant push (exclure
  `.env`, `wheels/`, `__pycache__`).

## Journal
- 2026-08-28 : fichier créé.
- 2026-08-28 : **PHASE A FAITE** — `BDD_GeoCorrections` (23), `BDD_Departements`
  +latitude/longitude (101), `BDD_Regions` (18).
- 2026-08-28 : **PHASES B + C FAITES** — 4 fichiers adaptés (types,
  reference_repository, geo_service, restitution_service), rebuild + boot healthy,
  vérif Grist 11/11 et repli 17/17. **Étape 3 terminée.**
- 2026-08-28 (REVUE) : `BDD_GeoCorrections` jugée peu propre + **redondante** →
  **table SUPPRIMÉE** et mécanisme de corrections retiré du code (5 fichiers +
  tests). GIP ADINE (Agence Départementale) rattachée à l'**Aveyron** + coords de
  Rodez (BAN) sur sa fiche. Rebuild + payload vérifié : **258/258 placées**,
  healthy, rendu identique. Design final : coordonnées sur les fiches, replis
  préfecture/région via `BDD_Departements`+lat/long et `BDD_Regions`.
