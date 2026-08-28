# 10. Cadrage de la bascule SSO — droits, provisioning, mails

> Document de **cadrage** pour valider en copil, avant d'écrire du code.
> Complète `07_STRATEGIE_AUTH.md` (stratégie multi-mode) en figeant la cible SSO.
> Date : 2026-08-27.

---

## 1. Acquis

- **SSO uniquement** : décidé en copil ; confirmé par Victor le 2026-08-27
  (plus de mot de passe, ni d'email/magic link à gérer dans l'app).
- **Deux Keycloak, un seul code** :
  - un **Keycloak local** (docker-compose du dev FDR) sert **uniquement à tester
    le SSO en dev** ;
  - en **production**, l'app se branchera sur le **SSO propre de France Data
    Réseau** (lui aussi un Keycloak).
  → Grâce au connecteur OIDC **générique** (`oidc_service.py`), c'est la MÊME app
    dans les deux cas : on ne change que les 3 variables `OIDC_*` du `.env` selon
    l'environnement. **Aucun code spécifique à un IdP.**
- **Responsabilités qui en découlent** : **FDR gère les comptes** (dans son
  Keycloak) ; **nous gérons les droits** dans Grist → conforte le **Modèle A**.

---

## 2. Décision CENTRALE — où vivent les droits ?

Les droits actuels (`Administrateur`, `Editeur`, `Visiteur`, `Extention`,
`En attente`) contrôlent l'édition, la validation des comptes et le périmètre de
chacun. Trois modèles :

| Modèle | Identité | Droits | Rattachement collectivité |
|---|---|---|---|
| **A** | Keycloak | **Grist** (`BDD_Utilisateurs.droits`) | Grist |
| **B** | Keycloak | **Keycloak** (rôles/groupes) | Grist (obligé) |
| **C** | Keycloak | hybride | Grist |

### → Recommandation : **Modèle A** (identité au SSO, autorisation dans Grist)

**Pourquoi :**
1. L'app a **de toute façon** besoin d'une ligne Grist par utilisateur — le
   **rattachement à une collectivité** (`BDD_Utilisateurs.collectivite`) est
   indispensable aux contrôles d'accès (anti-IDOR : un éditeur n'édite QUE sa
   collectivité). Cette info est métier et ne peut vivre que dans Grist.
2. Les **admins FNCCR** gèrent déjà les droits dans **Grist** (outil qu'ils
   connaissent), sans avoir à toucher à la console Keycloak.
3. Le **connecteur OIDC existant fait déjà exactement ça** : email vérifié par
   l'IdP → mapping `BDD_Utilisateurs` → droits. Rien à réinventer.

Le modèle B (rôles dans Keycloak) forcerait quand même une ligne Grist pour la
collectivité, **plus** une gestion de rôles côté Keycloak : deux endroits à
maintenir, sans gain réel ici.

---

## 3. Décision — provisioning des comptes → **liste fermée** (tranché 2026-08-27)

**Décision de Victor :** ce sont les **admins** qui créent les comptes (éditeurs).
**Pas de création automatique** de compte à la connexion.

- Email **présent** dans `BDD_Utilisateurs` (saisi par un admin) → connexion OK,
  avec ses droits.
- Email **inconnu** au retour du SSO → **accès refusé** (« votre compte n'est pas
  encore autorisé, contactez un administrateur »). Aucune ligne créée d'office.
- **Formulaire d'inscription** : **conservé dans le code (« en stock ») mais plus
  affiché ni accessible** — lien retiré de la page de login, routes `/inscription`
  désactivées. Réactivable plus tard si besoin.

⚠️ **Process à formaliser** : ajouter un éditeur = **deux gestes** — (1) une ligne
`BDD_Utilisateurs` côté FNCCR (email + collectivité + droit) **et** (2) un compte
côté Keycloak FDR (même email). Voir §7.

---

## 4. Décision — envoi de mails

### → Recommandation : **optionnel, réduit au minimum**

- **Magic link** : supprimé (SSO uniquement).
- **Notification admin** d'une nouvelle demande (« En attente ») : utile mais
  **pas indispensable** — l'admin peut consulter la liste des « En attente » dans
  la console admin. Si on garde la notif → petit SMTP dédié (Brevo, car le M365
  en auth basique est cassé).
- **Sans besoin de mail confirmé, on peut ne PAS configurer de SMTP** →
  simplification.

---

## 5. Conséquences sur le code *(synthèse — aucune action engagée)*

**À retirer** (une fois le SSO validé en prod) :
- login mot de passe + `password_service.py` + colonne `password_hash` ;
- magic link (`magic_link_service.py`).

**À désactiver mais GARDER dans le code (« en stock ») :**
- formulaire d'inscription : routes `/inscription`, `inscription.html`,
  `InscriptionForm`, `register()` — non montés / non affichés, mais conservés ;
- `request_elevation()` (demande d'élévation en self-service) — désactivé :
  l'**élévation des droits se fait par l'admin** (décision Victor).

**À adapter :**
- `sso_callback` : email inconnu → **accès refusé** (plus de redirection vers
  l'inscription) ;
- `oidc_service.py` : branché sur Keycloak (dev) puis IdP FDR (prod) via `.env`.

**À garder :**
- mapping email vérifié → `BDD_Utilisateurs` (référentiel des droits) ;
- droits + rattachement collectivité dans Grist ;
- contrôles d'accès anti-IDOR ;
- **console admin** : attribution et élévation des droits par l'admin (le canal
  officiel de gestion des droits).

---

## 6. Flux cible (Modèle A)

```
Utilisateur ──> Keycloak / IdP FDR (authentification)
                     │  (email vérifié)
                     ▼
        L'app cherche l'email dans BDD_Utilisateurs
             │                         │
     trouvé  ▼                         ▼  absent
  session ouverte                accès refusé
  avec ses droits                « compte non autorisé,
  (anti-IDOR selon                 contactez un admin »
   sa collectivité)               (aucune création auto)
```

---

## 7. Points à confirmer (copil / dev FDR)

- [x] ~~Keycloak = IdP définitif, ou dev seulement ?~~ → **Réglé** : Keycloak
      local = dev/test ; en prod, SSO propre de FDR (Keycloak). Même code, config
      `.env` différente par environnement.
- [x] ~~Modèle A~~ → **validé** (droits dans Grist).
- [x] ~~Provisioning~~ → **liste fermée** : les admins créent les comptes ; pas de
      création auto ; email inconnu = accès refusé.
- [x] ~~request_elevation self-service~~ → **retiré du parcours** : l'élévation se
      fait par l'admin (fonction conservée en stock si besoin).
- [x] ~~Besoin de mail~~ → magic link supprimé ; pas de demande d'accès entrante
      → **notif admin inutile, SMTP non requis**.
- [ ] **Process d'ajout d'un éditeur** : qui crée la ligne Grist (admin FNCCR) et
      qui crée le compte Keycloak (FDR) — à formaliser.
- [ ] **Liste des admins FNCCR** (emails + noms) — à fournir par Victor.
