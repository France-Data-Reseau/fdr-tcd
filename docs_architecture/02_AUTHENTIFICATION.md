# Authentification — décision et plan

> Révisé suite aux revues du 2026-06-12 (`revues/`) : design d'usage unique précisé (S1),
> consommation par POST (S2), SMTP traité comme composant vital (S4).
>
> **Mise à jour 2026-06-13 — auth par mot de passe ajoutée (mode actif).** Vue
> d'ensemble multi-mode et migration : `07_STRATEGIE_AUTH.md`. État des modes :
> mot de passe = **actif** ; magic link = repli, bloqué tant que le SMTP est en
> panne ; SSO OIDC = cible, inerte en attente des identifiants FDR.

## Mode actif : mot de passe (décision Victor du 2026-06-13)

Le SMTP étant en panne (le magic link ne peut pas être envoyé), une
authentification classique par mot de passe a été ajoutée pour débloquer la
connexion. Elle s'intègre au pipeline commun (email vérifié → mapping
`BDD_Utilisateurs` → session) : c'est une 3ᵉ « preuve d'identité », pas une
refonte.

- **Stockage** : colonne `password_hash` ajoutée à `BDD_Utilisateurs` **via
  l'API** (décision Victor ; modification de schéma assumée, « pour le moment »).
  Compromis accepté : les hash sont visibles par les admins de l'instance Grist
  FDR — atténué par argon2id + politique de robustesse.
- **Hachage** : `argon2id` (`argon2-cffi`), paramètres OWASP. Le hash ne sort
  jamais de `password_service.py` (ni logs, ni API, ni templates).
- **Politique** : ≥ 12 caractères + refus d'une liste de mots de passe communs
  (NIST 2024). Dummy-verify sur email inconnu/sans hash (anti-timing).
- **Flux** : inscription enrichie (mot de passe + confirmation) → compte
  « En attente » → validation admin (inchangé). Login = email + mot de passe,
  message d'échec neutre commun (anti-énumération). Changement de mot de passe
  depuis le menu (`/mon-mot-de-passe`), sans SMTP.
- **Reset** : **aucun flux dans l'app** (décision Victor). Bootstrap des comptes
  existants (sans hash) et dépannage : utilitaire admin en ligne de commande
  `scripts/definir_mot_de_passe.py` (interactif). Le reset par email reviendra
  via le magic link quand le SMTP sera réparé.
- **Déploiement** (ordre impératif) : 1) export Grist ; 2)
  `scripts/ajouter_colonne_password.py` (crée la colonne) ; 3) déployer le code ;
  4) `scripts/definir_mot_de_passe.py` pour le compte admin. Écrire dans une
  colonne inexistante échouerait — la colonne doit précéder le code.

## Rappel du problème

L'auth v1 (email seul, sans preuve de possession) était LA faille majeure : quiconque connaît
l'email d'un utilisateur validé entre à sa place. La V2 la remplace. Quel que soit le mécanisme,
**`BDD_Utilisateurs` reste le référentiel des rôles** (correspondance par email) avec le même
workflow : inscription → `En attente` → validation admin.

## Décision actée (Victor)

> « Identification par SSO de Grist, en attendant on peut faire du magic link. »

### Précision importante sur le « SSO de Grist »

Grist (y compris `grist.francedatareseau.fr`) **n'est pas un fournisseur d'identité** : il
n'expose pas d'endpoint OIDC auquel une application tierce peut déléguer le login. Cette
instance Grist est elle-même *cliente* d'un IdP (celui de France Data Réseau — Keycloak,
ProConnect ou équivalent). « Se connecter avec son compte Grist » signifie donc en pratique :
**se brancher sur l'IdP qui est derrière cette instance Grist**.

C'est faisable via le flux OIDC générique prévu, mais il faut obtenir de l'opérateur de
`grist.francedatareseau.fr` :
- l'URL de l'issuer OIDC ;
- l'enregistrement de notre application comme client : `client_id` / `client_secret`,
  redirect URI `https://fdr2.revorun.eu/auth/callback`.

→ **Action Victor (non bloquante)** : demander à France Data Réseau.

## Plan en deux temps (sans refonte entre les deux)

### Temps 1 — Magic link (livré avec la V2)

Flux : l'utilisateur saisit son email → s'il correspond à un compte, un lien signé lui est
envoyé → le lien ouvre une **page de confirmation** → le clic sur le bouton ouvre la session.

**Design précisé (réponses aux revues S1/S2) :**

1. **Usage unique réel** — `itsdangerous` est sans état : il signe, il ne « consomme » rien.
   L'usage unique est donc garanti par DEUX mécanismes côté serveur :
   - un **magasin mémoire des jetons consommés** (viable car mono-worker — contrainte
     verrouillée, voir `01` §2) ;
   - chaque jeton embarque un **identifiant de démarrage du processus** (boot-id) : après un
     redémarrage du conteneur, tous les jetons antérieurs sont refusés. Cela ferme la fenêtre
     de rejeu post-redémarrage signalée en revue, au prix négligeable de redemander un lien
     après un déploiement (TTL 15 min de toute façon).
   - *Option (nécessite l'accord de Victor car modification de schéma)* : une colonne
     `last_login` dans `BDD_Utilisateurs` rendrait l'invalidation persistante. Non retenue
     par défaut — le boot-id suffit.
2. **Consommation par POST, jamais par GET** — les passerelles de sécurité mail (SafeLinks…)
   préchargent les liens : un GET qui consomme brûlerait le jeton avant le clic de
   l'utilisateur. `/auth/verifier` en GET affiche une page de confirmation (aucun effet de
   bord) ; seul le POST du bouton vérifie et consomme le jeton, puis ouvre la session.
3. **URL du lien construite exclusivement depuis `APP_PUBLIC_URL`** (`.env`), jamais depuis
   le header Host de la requête — parade à l'empoisonnement d'en-tête (lien piégé vers un
   domaine attaquant qui capturerait le jeton).
4. **Session régénérée à la connexion** (anti-fixation) ; jeton signé avec un **salt dédié**
   distinct de celui des sessions (rotation de `SECRET_KEY` possible par liste de clés).
5. **Rate limiting double** : par IP **et** par email ciblé (anti mail-bombing d'une victime).
6. **Réponse neutre** « si ce compte existe, un lien a été envoyé » → pas d'énumération
   d'emails, au login comme à l'inscription.
7. Le jeton transite en URL donc dans les access logs de Caddy : risque borné par TTL 15 min
   + usage unique + consommation POST ; rétention courte des logs côté VPS.

**SMTP = composant vital (S4)** — avec le magic link, pas d'email = pas de connexion :
- les variables `SMTP_*` sont **vérifiées au démarrage en production**, au même titre que
  `SECRET_KEY` (refus de démarrer sinon) ;
- échec d'envoi à l'exécution : message neutre côté utilisateur, journalisation sobre,
  jamais de 500 ;
- délivrabilité = risque opérationnel n°1 : un expéditeur Gmail vers des domaines de
  collectivités (filtres stricts) risque le spam. Recommandation : expéditeur aligné
  SPF/DKIM (sous-domaine dédié de `revorun.eu` via un relais transactionnel — offres
  gratuites suffisantes à cette échelle). Le mot de passe d'application Gmail reste
  acceptable pour le développement. **→ choix expéditeur : Victor.**

Limites assumées : pas de MFA ; sécurité = celle de la boîte mail de l'utilisateur.
Suffisant pour des données semi-publiques + rôles validés par admin.

### Temps 2 — SSO OIDC ✅ IMPLÉMENTÉ (en attente des identifiants IdP)

- `services/oidc_service.py` (fastapi-oidc) + routes `/auth/sso` et `/auth/callback`
  + bouton « Se connecter avec France Data Réseau » sur la page de login.
- **Activation par simple configuration** : le SSO est inerte tant que
  `OIDC_ISSUER` / `OIDC_CLIENT_ID` / `OIDC_CLIENT_SECRET` sont vides dans le
  `.env` ; les renseigner fait apparaître le bouton — zéro changement de code.
- Redirect URI bâtie sur `APP_PUBLIC_URL` uniquement ; state/nonce gérés en
  session signée ; id_token validé avec fastapi-oidc ; emails explicitement non
  vérifiés refusés.
- Email vérifié par l'IdP → même pipeline que le magic link (mapping
  `BDD_Utilisateurs`) ; email sans compte → demande d'accès pré-remplie.
- Le magic link reste actif en repli (utilisateurs sans compte FDR).
- **Reste à obtenir de France Data Réseau** : l'URL de l'issuer OIDC et
  l'enregistrement de l'app comme client (redirect URI
  `https://fdr2.revorun.eu/auth/callback`).

## Options étudiées (pour mémoire)

| Option | Avantages | Inconvénients | Statut |
|---|---|---|---|
| A. ProConnect/AgentConnect | Auth forte état, public cible = agents publics, zéro infra | Habilitation datapass (semaines), exclut les non-agents | Possible plus tard via le même flux OIDC générique |
| B. IdP auto-hébergé (Authentik/Keycloak) | Tous emails, MFA, souveraineté | Un service lourd de plus à exploiter sur le VPS (~1 Go RAM + Postgres) | Écarté tant que l'IdP FDR est envisageable |
| C. Magic link | Simple, zéro infra nouvelle, corrige la faille v1 immédiatement | Délivrabilité email, pas de MFA | **Retenu (temps 1)** |
| SSO via IdP de France Data Réseau | Comptes existants des utilisateurs Grist, cohérence écosystème | Dépend de l'opérateur FDR (enregistrement client) | **Cible (temps 2)** |
