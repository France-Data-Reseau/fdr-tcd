# Authentification — SSO OIDC uniquement

> Mise a jour : 2026-06-13
> Cette application utilise desormais un seul mode d'authentification :
> SSO OIDC (Authorization Code + PKCE S256).

## 1. Decision actuelle

- Le login applicatif par mot de passe est retire.
- Le login par magic link est retire.
- Le point d'entree utilisateur est la page login, qui demarre ensuite le flux OIDC.
- Le role applicatif reste resolu via BDD_Utilisateurs (email comme cle de correspondance).

## 2. Flux d'authentification

1. L'utilisateur ouvre la page login.
2. L'utilisateur clique sur le bouton SSO.
3. L'application appelle /auth/sso.
4. Le service OIDC genere state, nonce et PKCE (code_verifier/code_challenge S256).
5. Redirection vers l'IdP France Data Reseau.
6. L'IdP renvoie vers /auth/callback avec le code d'autorisation.
7. L'application echange le code (avec code_verifier), valide l'id_token, verifie email_verified.
8. Si l'email est connu dans BDD_Utilisateurs, ouverture de session.
9. Sinon, redirection vers inscription/demande d'acces.

## 3. Invariants de securite

- PKCE S256 actif.
- state et nonce verifies.
- Session regeneree a la connexion.
- Email non verifie cote IdP refuse.
- Messages d'erreur sobers (pas de details techniques sensibles).
- En cas d'indisponibilite OIDC au demarrage du flux, retour vers login avec message utilisateur, sans 500.

## 4. Configuration

Variables principales :

- APP_PUBLIC_URL
- OIDC_ISSUER
- OIDC_CLIENT_ID
- OIDC_CLIENT_SECRET (optionnel pour un client public)

Notes :

- Les redirect URI doivent etre coherentes entre APP_PUBLIC_URL et la configuration client de l'IdP.
- En client public, OIDC_CLIENT_SECRET peut rester vide.

## 5. Roles applicatifs (inchanges)

BDD_Utilisateurs reste la source de verite des droits.

- Administrateur
- Editeur
- Visiteur
- Extention
- En attente

Le role n'est pas derive de l'IdP, il est applique par l'application apres mapping email.

## 6. Points operationnels

- Le SSO depend de la disponibilite de l'IdP.
- Le runbook de depannage doit couvrir : metadata OIDC inaccessible, redirect URI invalide, horloge systeme desync.
- Les tests couvrent le chemin nominal, les erreurs de callback, et le mode client public PKCE.
