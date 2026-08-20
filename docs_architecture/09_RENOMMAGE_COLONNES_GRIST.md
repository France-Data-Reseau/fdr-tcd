# 09. Renommage des colonnes Grist — extract et proposition

> Prépare la tâche différée n°1 (nettoyage des noms de colonnes). Extract de
> l'état RÉEL au 2026-06-13 (via `scripts/extract_colonnes.py`, lecture seule)
> + proposition d'identifiants plus propres et cohérents.
>
> ⚠️ **Le document Grist est PARTAGÉ entre la V1 (`fdr.revorun.eu`) et la V2.**
> Renommer une colonne impacte les DEUX applications. Rien ne se renomme sans
> (a) l'accord de Victor, (b) la coordination avec l'agent de la V1 (voir
> `COORDINATION_V1_RENOMMAGE.md`), (c) une sauvegarde Grist préalable.

## Conventions retenues pour la proposition

1. **snake_case minuscule** partout (corrige les CamelCase : `Nom`→`nom`,
   `Email`→`email`, `Droits`→`droits`…).
2. **Suppression de l'artefact `_s_`** (pluriel Grist mal formé) → vrai pluriel
   ou nom clair : `projet_s_`→`projets`, `role_s_`→`roles`,
   `collectivite_s_porteuse_s_`→`collectivites_porteuses`.
3. **Singulier pour les Ref simples, pluriel pour les RefList**
   (`collectivite_s_`→`collectivite` car Ref simple ; `contrat`→`contrats` car
   RefList).
4. **Clarification des abréviations** : `dep`→`departement`, `reg`→`region`,
   `en_ligne`→`lien`, `cas_d_usage`→`cas_usages`, `prenom_nom`→`nom_complet`,
   `Document_fichier_`→`fichier`.
5. **Conservation des codes métier FNCCR** : les 7 booléens compétences
   (`fnccr`, `num`, `eau`, `aode`, `tre`, `ep`, `dec`) et `siren` restent tels
   quels (vocabulaire connu).

## Colonnes système — NE PAS TOUCHER

Présentes dans chaque table, gérées par Grist (hors mapping ci-dessous) :
- **`manualSort`** (type `ManualSortPos`) : ordre manuel des lignes.
- **`gristHelper_Display*`** (type `Any`, formules `$ref.colonne`) : colonnes
  d'affichage auto-générées pour les références (display formulas, piège n°4).
  Grist les régénère/met à jour lui-même quand on renomme une colonne Ref via
  l'action de renommage appropriée.

## Mapping proposé (par table)

> Légende type : `T`=Text, `Num`=Numeric, `B`=Bool, `C`=Choice, `CL`=ChoiceList,
> `Ref:X`=référence simple, `RefL:X`=RefList, `(F)`=colonne formule.

### BDD_CasUsages
| ID actuel | Type | ID proposé | Note |
|---|---|---|---|
| nom | T | nom | inchangé |
| theme | CL | theme | inchangé |
| projets | RefL:Projets | projets | inchangé |
| domaine | C | domaine | inchangé |
| Connectivites | RefL:Connectivites | connectivites | casse |

### BDD_Collectivites
| ID actuel | Type | ID proposé | Note |
|---|---|---|---|
| nom | T | nom | inchangé |
| siren | Num | siren | inchangé |
| logo | T | logo | inchangé |
| url_logo | T | url_logo | inchangé |
| statut | CL | statut | inchangé |
| couverture | C | couverture | inchangé |
| num_dep | T (F) | num_dep | **formule** `$dep.num_dep` → suit le renommage de `dep` |
| dep | Ref:Departements | departement | clarté ; **référencé par 3 formules** (voir §formules) |
| reg | C (F) | region | **formule** `$dep.region` |
| site_web | T | site_web | inchangé |
| adresse | T | adresse | inchangé |
| lat | T | latitude | clarté |
| long | T | longitude | clarté |
| projet_s_ | RefL:Projets | projets | `_s_` |
| fnccr,num,eau,aode,tre,ep,dec | B | (inchangés) | codes métier FNCCR |

### BDD_Connectivites
| ID actuel | Type | ID proposé | Note |
|---|---|---|---|
| Nom | T | nom | casse |
| projets | RefL:Projets | projets | inchangé |

### BDD_Contacts
| ID actuel | Type | ID proposé | Note |
|---|---|---|---|
| prenom_nom | T (F) | nom_complet | **formule** `($prenom+" "+$nom).strip()` |
| elu_e | B | elu | simplification |
| collectivite_s_ | Ref:Collectivites | collectivite | `_s_` + Ref simple → singulier |
| prenom | T | prenom | inchangé |
| nom | T | nom | inchangé |
| fonction | T | fonction | inchangé |
| email | T | email | inchangé |
| telephone | T | telephone | inchangé |
| mobile | T | mobile | inchangé |
| projet_s_ | **RefL:Projets** | projets | `_s_`. ⚠️ **INCOHÉRENCE** : le type réel est RefList, mais le code V1 ET V2 l'utilise comme un Text (nom du projet). À clarifier AVANT renommage (voir §points d'attention). |

### BDD_Contrats
| ID actuel | Type | ID proposé | Note |
|---|---|---|---|
| nom | T | nom | inchangé |

### BDD_Departements
| ID actuel | Type | ID proposé | Note |
|---|---|---|---|
| num_dep | T | num_dep | inchangé ; **référencé** par `Collectivites.num_dep` |
| nom | T | nom | inchangé |
| region | T | region | inchangé ; **référencé** par `Projets.region` et `Collectivites.reg` |
| projets | RefL (F) | projets | **formule lookup** `…departement_s_=CONTAINS($id)` → suit le renommage de `Projets.departement_s_` |

### BDD_Documents
| ID actuel | Type | ID proposé | Note |
|---|---|---|---|
| titre | T | titre | inchangé |
| en_ligne | T | lien | clarté (URL du document) |
| projet | Ref:Projets | projet | inchangé (Ref simple) |
| type | CL | type | inchangé |
| annee | Num | annee | inchangé |
| Document_fichier_ | Attachments | fichier | casse + `_` (non exposé par l'app) |

### BDD_Partenaires
| ID actuel | Type | ID proposé | Note |
|---|---|---|---|
| nom | T | nom | inchangé |
| role_s_ | CL | roles | `_s_` |
| url | T | url | inchangé |
| Projets | RefL:Projets | projets | casse ; **référencé** par `Projets.partenaire_s_` (lookup `Projets=CONTAINS`) |

### BDD_Programmes
| ID actuel | Type | ID proposé | Note |
|---|---|---|---|
| nom | T | nom | inchangé |
| info_web | T | info_web | inchangé |
| echelle | C | echelle | inchangé |
| projet_s_ | RefL:Projets | projets | `_s_` |

### BDD_Projets
| ID actuel | Type | ID proposé | Note |
|---|---|---|---|
| nom | T | nom | inchangé |
| collectivite_s_porteuse_s_ | RefL:Collectivites | collectivites_porteuses | `_s_…_s_` |
| contact_s_ | RefL:Contacts | contacts | `_s_` |
| description | T | description | inchangé |
| connectivite_s_ | RefL:Connectivites | connectivites | `_s_` |
| Theme_s_ | CL (F) | themes | casse + `_s_` ; **formule** sur `cas_d_usage` |
| avancement | C | avancement | inchangé |
| partenaire_s_ | RefL (F) | partenaires | **formule lookup** sur `Partenaires.Projets` |
| dev_interne | B | dev_interne | inchangé |
| solution_s_ | RefL:Solutions | solutions | `_s_` ; **référencé** par `Solutions.projets` |
| cas_d_usage | RefL (F) | cas_usages | **formule lookup** sur `CasUsages.projets` |
| echelle | C | echelle | inchangé |
| mutualisation | CL | mutualisation | inchangé |
| soutien | C | soutien | inchangé |
| programme_s_ | RefL:Programmes | programmes | `_s_` |
| contrat | RefL:Contrats | contrats | RefList → pluriel |
| departement_s_ | RefL:Departements | departements | `_s_` ; **référencé** par `Departements.projets` (lookup) |
| region | T (F) | region | **formule** sur `departement_s_` |
| document_s_ | RefL:Documents | documents | `_s_` |

### BDD_Solutions
| ID actuel | Type | ID proposé | Note |
|---|---|---|---|
| nom | T | nom | inchangé |
| type | C | type | inchangé |
| partenaire | Ref:Partenaires | partenaire | inchangé (Ref simple) |
| projets | RefL (F) | projets | **formule lookup** `…solution_s_=CONTAINS($id)` → suit le renommage de `Projets.solution_s_` |

### BDD_Utilisateurs
| ID actuel | Type | ID proposé | Note |
|---|---|---|---|
| Nom | T | nom | casse |
| Prenom | T | prenom | casse |
| Organisation | T | organisation | casse |
| Email | T | email | casse |
| Droits | C | droits | casse |
| Collectivite | Ref:Collectivites | collectivite | casse |
| Date_inscription | T | date_inscription | casse |

## Dépendances de formules (cross-table) — CRITIQUE

Renommer une colonne référencée par une formule d'une AUTRE table casse cette
formule si elle n'est pas mise à jour en même temps. Les chaînes à traiter
ensemble :

- `Projets.departement_s_` ↔ `Departements.projets` (lookup) + `Projets.region`
  + `Collectivites.num_dep`/`reg` (via `dep`).
- `Projets.solution_s_` ↔ `Solutions.projets` (lookup).
- `Projets.cas_d_usage` ↔ `CasUsages.projets` (lookup) + `Projets.Theme_s_`.
- `Partenaires.Projets` ↔ `Projets.partenaire_s_` (lookup).
- `Collectivites.dep` → `Collectivites.num_dep` et `reg` (formules locales).
- `Contacts.prenom/nom` → `Contacts.prenom_nom`.

Grist met normalement à jour les formules automatiquement lors d'un renommage
via l'**action de renommage** (pas un simple PATCH de label). À VALIDER sur une
copie du document avant de toucher la prod.

## Procédure technique de renommage (à exécuter le moment venu)

1. **Sauvegarde Grist** (`scripts/export_grist.py`) + idéalement tester sur une
   COPIE du document d'abord.
2. Renommer **via l'API**, en utilisant l'action de renommage de colonne (qui
   propage aux formules et aux `gristHelper_Display`), table par table.
   ⚠️ Un simple changement de `label` ne change pas l'`id` (= ce que le code
   utilise) ; il faut l'action qui change l'`id` de la colonne.
3. Mettre à jour **le code V2** de façon synchronisée :
   `repositories/types.py` (TypedDicts + `COL_*`), `scripts/check_grist_schema.py`
   (`SCHEMA_ATTENDU`), services, templates, fixtures de tests.
4. Mettre à jour **le code V1** (voir `COORDINATION_V1_RENOMMAGE.md`).
5. Vérifier : `check_grist_schema` (V2 et V1), tests, et les deux apps en ligne.

## Points d'attention

- **`Contacts.projet_s_` — type ambigu** : l'extract le donne en `RefList:Projets`,
  mais le code V1 (commentaire « projet_s_ est de type Text ») et le code V2
  (`contact_repository.for_projet_nom`) l'utilisent comme un texte (nom du
  projet). Soit le type a changé après coup, soit l'usage est erroné. **À
  clarifier avec Victor avant tout renommage** : décider si la liaison
  contacts↔projets devient une vraie Ref (mieux) ou reste un texte.
- **Noms de TABLES** (`BDD_*`, `BDD_CasUsages` en CamelCase) : hors scope de ce
  document. Les renommer est plus risqué (référencés en dur dans les formules
  `BDD_Projets.lookupRecords(...)`). À traiter séparément si souhaité.
- **Stratégie de transition** : tant que la V1 tourne sur le même document, un
  renommage « big bang » crée une fenêtre où l'une des apps est cassée. Options
  dans `COORDINATION_V1_RENOMMAGE.md` §stratégie.
