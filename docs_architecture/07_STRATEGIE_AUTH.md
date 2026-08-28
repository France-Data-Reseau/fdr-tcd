# 07. Stratégie d'authentification multi-mode et migration

> But de ce document : permettre à un repreneur de **changer de mode
> d'authentification** (en ajouter un, en retirer un, basculer de l'un à
> l'autre) sans rien casser. Complète `02_AUTHENTIFICATION.md` (qui décrit
> chaque mode en détail). Dernière mise à jour : 2026-06-13.

## 1. Le principe : un pipeline commun, des « preuves d'identité » interchangeables

C'est l'idée structurante de toute l'authentification de l'app. **Chaque mode
d'authentification ne fait qu'une chose : produire un EMAIL VÉRIFIÉ.** À partir
de là, le chemin est rigoureusement identique quel que soit le mode :

```
  [preuve d'identité selon le mode]
        │
        ▼
  email vérifié
        │
        ▼
  mapping BDD_Utilisateurs   ← repository.get_by_email(email)
  (référentiel des rôles)       l'email est la clé unique
        │
        ▼
  ouverture de session       ← open_user_session(request, email)
  (identité SEULE en session)   le rôle est re-résolu à CHAQUE requête
        │
        ▼
  workflow inchangé          ← « En attente » → validation admin
```

Conséquence directe et précieuse : **ajouter ou retirer un mode ne touche QUE
la couche « preuve d'identité »** (un service + des routes). Le mapping des
rôles, les sessions, le workflow de validation, l'anti-IDOR : rien ne bouge.

Invariant à ne jamais enfreindre : **`BDD_Utilisateurs` reste l'unique
référentiel des rôles**, et **l'email est la clé de correspondance** entre tout
mode d'auth et le compte applicatif.

## 2. Les modes et leur état

| Mode | Preuve d'identité produite | Code | État au 2026-06-13 | Bascule on/off |
|---|---|---|---|---|
| **Mot de passe** | hash vérifié (argon2id) | `services/password_service.py` (proposé) | À implémenter (décision de stockage en cours) | actif si la colonne/le store de hash existe |
| **Magic link** | jeton email signé + consommé | `services/magic_link_service.py` | Implémenté, **bloqué** (SMTP en panne) | actif si `SMTP_*` configurés |
| **SSO OIDC** | jeton de l'IdP France Data Réseau | `services/oidc_service.py` | Implémenté, **inerte** | actif si `OIDC_ISSUER`/`OIDC_CLIENT_ID`/`OIDC_CLIENT_SECRET` renseignés |

**Tous les modes peuvent COEXISTER.** La page de login présente simultanément
les options disponibles (ex. formulaire mot de passe + bouton SSO). Le choix
du mode est laissé à l'utilisateur ; le compte et le rôle qu'il retrouve sont
les mêmes quel que soit le mode (même email → même compte).

## 3. Comment chaque mode s'active / se désactive

Aucun de ces changements ne nécessite de toucher au code — uniquement le `.env`
du VPS (puis redémarrage du conteneur) :

- **Magic link** : présent dès que `SMTP_HOST`/`SMTP_USER`/`SMTP_PASSWORD` sont
  remplis. Vide ⇒ dormant (les fonctions journalisent et ne font rien).
- **SSO** : présent dès que les trois `OIDC_*` sont remplis
  (`oidc_service.enabled`). Le bouton n'apparaît que dans ce cas.
- **Mot de passe** : présent dès que le magasin de hash existe (selon la
  décision de stockage — voir §6). Le formulaire mot de passe est rendu
  conditionnellement, comme le bouton SSO.

> Pour qu'un mode disparaisse de la page login, il suffit de retirer sa
> condition d'activation (vider la variable d'env correspondante). Le code
> reste en place, prêt à être réactivé.

## 4. Scénarios de migration

### A. Aujourd'hui → mot de passe (débloquer la connexion sans SMTP)
1. Décider du stockage des hash (§6) ; si « colonne Grist », ajouter la
   colonne **via l'API** (jamais l'interface — piège n°1) après export Grist.
2. Déployer le mode mot de passe (formulaire d'inscription enrichi + login).
3. Les comptes EXISTANTS de `BDD_Utilisateurs` n'ont pas de hash : prévoir
   un chemin pour qu'ils s'en créent un (premier login → « définir mon mot
   de passe », ou reset admin selon §6). Les nouveaux comptes définissent leur
   mot de passe à l'inscription.

### B. Mot de passe → SSO France Data Réseau (quand FDR répond)
1. Renseigner les trois `OIDC_*` dans le `.env` du VPS, redémarrer. Le bouton
   « Se connecter avec France Data Réseau » apparaît automatiquement.
2. **Phase de coexistence** : SSO + mot de passe en repli. Les utilisateurs
   migrent à leur rythme — aucune action requise de leur part, **aucun
   re-mapping** : un utilisateur qui se connectait par mot de passe avec
   l'email X retrouve le même compte/rôle en se connectant par SSO avec X.
3. Quand tous les utilisateurs actifs passent par le SSO : on peut retirer le
   mode mot de passe (condition d'activation désactivée). **Ne purger la
   colonne/le store de hash qu'ensuite, et après sauvegarde** — décision Victor.

### C. Retour au magic link (si le SMTP est réparé)
Remplir `SMTP_*` et redémarrer. Le magic link redevient disponible. Utile
notamment comme **chemin de reset** du mot de passe (lien signé par email),
ce qui retire la dépendance au reset par admin (§6).

## 5. Points d'attention lors de toute bascule

- **L'email est la clé.** Un utilisateur dont l'email diffère entre l'IdP (SSO)
  et `BDD_Utilisateurs` ne sera pas reconnu (et sera orienté vers l'inscription).
  Vérifier la cohérence des emails AVANT de basculer en SSO.
- **Sessions inchangées entre modes** (identité seule, rôle re-résolu) : une
  bascule de mode ne déconnecte personne et ne change aucun rôle.
- **Anti-énumération** : tout nouveau mode doit garder des réponses neutres au
  login et à l'inscription (ne jamais révéler si un email a un compte).
- **Rate limiting + CSRF** : tout POST d'un nouveau mode reprend les mêmes
  garde-fous (slowapi par IP, CSRF de session).
- **Le hash de mot de passe ne sort jamais** : ni logs, ni API, ni templates,
  ni messages d'erreur (même règle que la clé API Grist).

## 6. Le mode mot de passe — décision de stockage (à acter avec Victor)

`BDD_Utilisateurs` n'a aucune colonne pour un mot de passe. Deux options, à
trancher (cf. la question posée en session du 2026-06-13) :

| Option | Principe | Avantages | Compromis |
|---|---|---|---|
| **A. Colonne dans Grist** | Ajouter `password_hash` (Text) à `BDD_Utilisateurs` **via l'API** | Cohérent (Grist = source unique), inclus dans l'export de sauvegarde, zéro infra | Modification de schéma (accord Victor) ; hash **visibles par les admins de l'instance Grist FDR** — atténué par argon2id + mots de passe forts |
| **B. Hors Grist (volume Docker)** | Hash dans un fichier/SQLite sur un volume persistant du conteneur | Hash invisibles côté Grist | Volume à sauvegarder séparément ; sort du modèle « Grist = source unique » ; perdu si le conteneur est recréé sans volume |

Variante de A (defense-in-depth, si souhaité) : stocker le hash **chiffré** avec
une clé du `.env` du serveur — même un admin Grist ne voit que du chiffré.
Ajoute une rotation de clé à gérer ; sans doute superflu à cette échelle.

**Paramètres communs quel que soit le stockage :**
- Hachage **argon2id** (`argon2-cffi`), paramètres OWASP par défaut.
- Politique « mot de passe fort » : **≥ 12 caractères** + refus d'une liste de
  mots de passe très communs (NIST 2024 : la longueur prime sur les règles de
  composition arbitraires). Vérification d'un dummy-hash sur email inexistant
  (anti timing-attack qui révélerait l'existence d'un compte).
- **Reset de mot de passe** (le SMTP est en panne) — deux approches, à trancher :
  - reset par l'**admin** depuis la console (mot de passe temporaire à
    transmettre hors-bande) : fonctionne sans SMTP, cohérent avec le workflow
    admin existant ;
  - **pas de reset** pour l'instant : on l'activera par magic link quand le
    SMTP reviendra (scénario C).

## 7. Brancher un NOUVEAU mode (recette d'implémentation)

1. Créer `app/services/<mode>_service.py` dont la seule responsabilité est de
   produire un **email vérifié** (et `enabled` selon la config).
2. Ajouter la fabrique `@lru_cache` dans `dependencies.py` (+ `reset_singletons`).
3. Ajouter les routes dans `app/api/auth.py` : elles appellent le service, puis
   `get_utilisateur_repository().get_by_email(email)`, puis `open_user_session`.
   **Ne pas réimplémenter** le mapping/les rôles/la session — tout existe.
4. Rendre l'option conditionnellement sur `login.html` (comme le bouton SSO).
5. Tests : réponses neutres, CSRF, accès `En attente` → acces-refuse, et le
   chemin nominal. S'inspirer de `tests/api/test_sso.py` (service stubé, zéro
   I/O réseau).
