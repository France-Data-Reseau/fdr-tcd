# Audit interface Complétion — Parcours collectivité test

> Scénario : nouvelle collectivité "Syndicat Test du Numérique (STN)" — Éditeur puis Administrateur
> Date de l'audit : 2026-04-02

---

## Résumé

| Catégorie | Critique | Sérieux | Mineur |
|---|:---:|:---:|:---:|
| Bugs | 3 | 5 | 4 |
| Améliorations UX | — | 5 | 7 |

---

## BUGS

### 🔴 Critique

---

#### BUG-01 — Contacts invisibles : jamais affichés sur la fiche projet

**Où** : `main.py` → `_get_sous_formulaires()` (ligne ~680) + `templates/projet_form.html`

**Ce qui se passe** : Les contacts peuvent être créés via `/projet/{id}/contact/nouveau` mais sont systématiquement absents de la fiche projet. La fonction `_get_sous_formulaires` retourne toujours une liste vide :
```python
result["contacts"] = []   # hardcodé, jamais alimenté depuis Grist
```
De plus, la section "Données liées" (`sub-links`) ne contient pas de carte Contacts — le lien n'est pas accessible depuis la fiche projet. Le seul moyen d'y accéder est l'URL directe.

**Impact** : Les contacts créés sont orphelins dans Grist, invisibles depuis l'interface.

**Correction** : Alimenter `result["contacts"]` depuis `grist.get_all_records("contacts")` filtré par `collectivite_s_ == collectivite_id`, et ajouter une carte "Contacts" dans `sous_formulaires` de `projet_form.html`.

---

#### BUG-02 — Bouton "Créer une collectivité" cassé depuis la page d'inscription

**Où** : `templates/inscription.html` ligne 45

**Ce qui se passe** : Le bouton `+ Créer une collectivité` de la page d'inscription pointe vers `/collectivite/nouveau?from=inscription`. Mais cette route est protégée par `require_editor()` : un utilisateur non encore connecté est immédiatement redirigé vers `/login`, perdant tout le contexte (formulaire d'inscription rempli, email pré-saisi).

**Impact** : Un nouvel utilisateur souhaitant d'abord créer sa collectivité avant de s'inscrire est bloqué.

**Correction** : Soit supprimer ce bouton depuis la page d'inscription (flow impossible pour un non-connecté), soit créer une route `/collectivite/nouveau` accessible sans auth (avec enregistrement différé côté session).

---

#### BUG-03 — Liaison d'un cas d'usage existant écrase sa liaison précédente

**Où** : `main.py` → `cas_usage_creer()` (ligne ~771)

**Ce qui se passe** : Quand on lie un cas d'usage existant à un projet, l'opération effectuée est :
```python
await grist.update_record("cas_d_usage", cas_id, {"projets": projet_id})
```
Le champ `projets` est une **Ref simple** (pas une RefList). Si ce cas d'usage était déjà lié à un autre projet, ce lien est **écrasé**. En production, cocher un cas d'usage populaire délierait silencieusement tous les autres projets qui l'utilisaient.

**Impact** : Corruption silencieuse de données — un cas d'usage ne peut être lié qu'à un seul projet à la fois.

**Correction** : Soit convertir `projets` en RefList dans le schéma Grist et utiliser `add_to_reflist`, soit informer l'utilisateur que ce cas d'usage est déjà utilisé par un autre projet.

---

### 🟠 Sérieux

---

#### BUG-04 — Soumission silencieuse du formulaire "Nouveau cas d'usage" si nom vide

**Où** : `main.py` → `cas_usage_creer()` (ligne ~776-789)

**Ce qui se passe** :
```python
nom = form.get("nouveau_nom", "")
if nom:
    # crée le cas d'usage
# else : aucun flash, redirect silencieux
```
Si l'utilisateur clique "Créer et retourner au projet" sans remplir le nom, il est redirigé vers la fiche projet sans message d'erreur. La même logique s'applique au partenaire nouveau (vérification `nom` absente) et au programme nouveau.

**Impact** : Des records vides peuvent être créés dans Grist (partenaire/programme), ou l'utilisateur pense avoir créé quelque chose qui n'existe pas (cas d'usage).

**Correction** : Ajouter une validation côté serveur + flash("error") si `nom` est vide.

---

#### BUG-05 — `dev_interne` — pré-remplissage fragile

**Où** : `templates/projet_form.html` ligne 122 + `main.py` → `parse_bool_field()`

**Ce qui se passe** : Le stockage est `parse_bool_field(form.get("dev_interne"))` qui retourne la chaîne `"checked"`. Le template vérifie `record.fields.dev_interne == 'checked'`. Si le champ Grist est nativement de type **Toggle** (booléen), Grist retourne `True` (Python bool) et non `"checked"` — la comparaison échoue, la case n'est jamais pré-cochée en édition.

**Impact** : La valeur "Développement interne" n'est jamais pré-remplie en mode édition (si le schéma Grist est Boolean/Toggle).

**Correction** : Stocker un vrai booléen (`True`/`False`) ou normaliser la lecture avec `bool(record.fields.get("dev_interne"))`.

---

#### BUG-06 — Région non réinitialisée quand le département est décoché (formulaire projet)

**Où** : `templates/projet_form.html` → fonction JS `autoFillRegion()`

**Ce qui se passe** :
```javascript
function autoFillRegion(select) {
    var val = select.value;
    if (val) {
        // auto-remplit la région
    }
    // else : rien — la région conserve sa valeur précédente
}
```
Si l'utilisateur sélectionne un département (région auto-remplie), puis repasse sur "—", la région ne se vide pas. Le formulaire collectivité (`updateDepFields`) gère correctement ce cas mais pas le formulaire projet.

**Impact** : Incohérence département/région après désélection.

**Correction** : Ajouter dans le bloc `else` : `document.getElementById('region').value = '';`

---

#### BUG-07 — Bouton "Retour" de la fiche collectivité mène au menu, pas à `/completion`

**Où** : `templates/collectivite.html` ligne 5-8

**Ce qui se passe** :
```html
<a href="/" class="btn-back">Retour à l'accueil</a>
```
Pour un Administrateur naviguant depuis `/completion`, le retour amène au menu principal (`/`) plutôt qu'à la liste des collectivités (`/completion`).

**Impact** : Navigation cassée pour les admins qui gèrent plusieurs collectivités.

**Correction** : Passer `referer` ou un paramètre `from=completion` dans l'URL, ou utiliser `href="/completion"` directement.

---

#### BUG-08 — Éditeur sans `collectivite_id` voit toute la liste des collectivités

**Où** : `main.py` → route `/completion` (ligne ~380)

**Ce qui se passe** :
```python
if user["droits"] == "Editeur" and user["collectivite_id"]:
    return RedirectResponse(url=f"/collectivite/{user['collectivite_id']}", ...)
```
Si `collectivite_id` vaut `0` (falsy), l'éditeur n'est pas redirigé et voit toute la liste. Il peut ensuite cliquer sur n'importe quelle collectivité — la vérification IDOR de la route GET `/collectivite/{id}` bloquera, mais l'interface est confuse.

**Impact** : UX trompeuse pour un éditeur sans collectivité assignée.

**Correction** : Gérer explicitement ce cas avec un message d'information ("Aucune collectivité n'est associée à votre compte — contactez un administrateur").

---

### 🟡 Mineur

---

#### BUG-09 — Partenaire/Programme : création possible sans nom

**Où** : `main.py` → `partenaire_creer()` et `programme_creer()`

**Ce qui se passe** : Aucune vérification `if nom:` côté serveur. Soumettre le formulaire "Nouveau partenaire" avec nom vide crée un record vide dans Grist. La contrainte `required` HTML5 peut être contournée par toute requête directe.

---

#### BUG-10 — `projet_s_` des contacts est un champ Text, pas une relation

**Où** : `main.py` → `contact_creer()` ligne ~1048-1050

**Ce qui se passe** : Le lien contact→projet est stocké comme le nom du projet en texte libre :
```python
fields["projet_s_"] = projet_nom   # Texte, pas une Ref Grist
```
Si le projet est renommé, le lien est perdu. On ne peut pas retrouver les contacts d'un projet par ID.

---

#### BUG-11 — Thème de filtre non conservé après "Enregistrer et continuer" (cas d'usage)

**Où** : `main.py` → `cas_usage_creer()` + `templates/cas_usage.html`

**Ce qui se passe** : Après `action=autre`, la redirection vers la même page ne préserve pas le thème sélectionné. L'utilisateur doit re-sélectionner le thème à chaque fois.

---

#### BUG-12 — Partenaires/Programmes existants non filtrés par collectivité

**Où** : `main.py` → `partenaire_nouveau()` et `programme_nouveau()`

**Ce qui se passe** : `grist.get_ref_records("partenaires")` retourne tous les partenaires de toutes les collectivités. Un éditeur peut par inadvertance lier à son projet un partenaire appartenant à une autre structure.

---

## AMÉLIORATIONS UX

### Haute priorité

---

#### UX-01 — Pas de fonctionnalité de suppression

Impossible de supprimer un projet, une collectivité, un contact, un cas d'usage, un partenaire, un programme ou un document. Le seul moyen est d'intervenir directement dans Grist. Cette absence bloque toute correction d'erreur de saisie.

**Suggestion** : Ajouter des boutons "Supprimer" avec confirmation modale sur les fiches et les items listés.

---

#### UX-02 — Pas d'édition possible des sous-formulaires

Une fois créés, les éléments liés (cas d'usage, partenaires, programmes, documents) ne peuvent être ni modifiés ni déliés depuis l'interface. Ils sont affichés en lecture seule dans les listes de la fiche projet.

**Suggestion** : Rendre chaque item cliquable avec une page d'édition dédiée.

---

#### UX-03 — Pas d'indicateur de complétion des fiches

L'interface s'appelle "Complétion" mais n'indique nulle part le niveau de remplissage d'une collectivité ou d'un projet. Un utilisateur ne sait pas ce qui manque.

**Suggestion** : Barre de progression calculée sur les champs obligatoires/recommandés. Ex : "6/10 champs renseignés".

---

#### UX-04 — Pas de protection contre le double-clic sur les boutons de soumission

Lors de soumissions lentes (API Grist), l'utilisateur peut double-cliquer sur "Enregistrer" et créer des doublons en base.

**Suggestion** : Désactiver le bouton après le premier clic (`disabled` via JS on submit).

---

#### UX-05 — Session expire sans avertissement

Après 1 heure d'inactivité, la session expire. Si l'utilisateur remplissait un long formulaire, il est redirigé vers `/login` sans message explicatif et perd toutes ses données.

**Suggestion** : Afficher une alerte modale à 5 minutes de l'expiration, avec bouton "Rester connecté" (appel silencieux à `/`).

---

### Moyenne priorité

---

#### UX-06 — Messages d'erreur génériques et non actionnables

Tous les blocs `except` affichent "Une erreur s'est produite. Veuillez réessayer." sans aucun contexte sur la nature du problème (timeout Grist ? Champ invalide ? Conflict ?).

**Suggestion** : Distinguer au minimum les erreurs réseau (retry) des erreurs de validation (feedback immédiat).

---

#### UX-07 — Liste des collectivités sans compteur de projets

La liste `/completion` affiche `[département — statut]` mais pas le nombre de projets associés. Difficile d'identifier rapidement les collectivités incomplètes.

**Suggestion** : Ajouter un badge `N projets` sur chaque item de la liste.

---

#### UX-08 — Pas de notification email lors des changements de statut

- Inscription → aucun email à l'administrateur
- Validation admin → aucun email à l'utilisateur
- Demande de modification → aucun email

**Suggestion** : Intégrer un envoi d'email minimal (smtp ou service tiers) sur ces trois événements.

---

#### UX-09 — Champ "Adresse" sans autocomplétion

L'API `api-adresse.data.gouv.fr` est déjà intégrée côté serveur pour le géocodage. Il est naturel de proposer l'autocomplétion côté client sur le champ adresse pour améliorer la qualité des données.

**Suggestion** : Ajouter un listener `input` sur le champ `adresse` avec appel à `https://api-adresse.data.gouv.fr/search/` et suggestions dans une datalist dynamique.

---

#### UX-10 — Pas de texte d'aide sur les champs métier

Les champs "Mutualisation", "Soutien", "Contrat", "Bénéficiaires", "Échelle" n'ont ni placeholder ni texte explicatif. Un utilisateur non familier du contexte FNCCR ne sait pas quoi renseigner.

**Suggestion** : Ajouter des `<small class="help-text">` sous chaque champ avec une description courte.

---

### Faible priorité

---

#### UX-11 — Validation SIREN absente côté client

Le champ SIREN accepte n'importe quel nombre. Pas de validation du format 9 chiffres.

**Suggestion** : Ajouter `minlength="9" maxlength="9" pattern="\d{9}"` sur l'input SIREN.

---

#### UX-12 — Bouton "Créer une collectivité" affiché en double dans accueil.html

Dans `accueil.html`, le bouton "+ Créer une nouvelle collectivité" apparaît à la fois dans le bloc `.no-results` (contextuel, correct) et systématiquement en bas de page. Pour un Éditeur, ce double affichage est redondant.

---

#### UX-13 — Pas de "warning" avant de quitter un formulaire modifié

Si l'utilisateur a modifié des champs et clique sur "Retour" ou ferme l'onglet, les modifications sont perdues sans avertissement.

**Suggestion** : Écouter `beforeunload` + détecter les changements via `change` events sur les champs.

---

## Flux complet testé

```
/login (email inconnu)
  → /inscription (pré-rempli email)
    → [BUG-02] Bouton "+ Créer collectivité" → bloqué

/login (email connu, Editeur, collectivite_id=0)
  → /completion
    → [BUG-08] Voit toute la liste sans redirection

/completion → /collectivite/nouveau
  → Création "Syndicat Test du Numérique"
  → Saisie SIREN "123456789" — accepté sans validation format
  → Sélection département "01 - Ain" → région auto-remplie ✓
  → Désélection département → région reste "Auvergne-Rhône-Alpes" [BUG-06]
  → Submit → flash "Collectivité créée !" ✓
  → Retour → "/" [BUG-07] (devrait être "/completion")

/collectivite/{id} → /projet/nouveau
  → Saisie nom projet, avancement, domaine ✓
  → Checkbox "Développement interne" cochée
  → Submit → flash "Projet créé !" ✓
  → /projet/{id}

/projet/{id} → Fiche projet
  → 4 cartes : Cas d'usage (0), Partenaires (0), Programmes (0), Documents (0)
  → Pas de carte "Contacts" [BUG-01]

  → /projet/{id}/cas-usage/nouveau
    → Sélection thème "Mobilité" → checkboxes affichées ✓
    → Coche cas d'usage existant → Submit
    → [BUG-03] : écrase la liaison précédente de ce cas d'usage
    → "Enregistrer et continuer" → thème perdu [BUG-11]
    → Formulaire "Nouveau" soumis vide → redirect silencieux [BUG-04]

  → /projet/{id}/partenaire/nouveau
    → Liste de TOUS les partenaires [BUG-12]
    → Submit nouveau partenaire sans nom → record vide créé [BUG-09]

  → /projet/{id}/contact/nouveau
    → Formulaire rempli → Submit ✓
    → Retour au projet → contact introuvable [BUG-01]

  → Édition projet → dev_interne non pré-coché [BUG-05]
```
