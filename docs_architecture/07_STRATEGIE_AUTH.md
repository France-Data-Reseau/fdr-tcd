# 07. Strategie d'authentification

> Mise a jour : 2026-06-13
> Document de pilotage pour maintenir l'authentification dans sa forme actuelle
> et encadrer une evolution future sans regression.

## 1. Etat courant

- Mode unique actif : SSO OIDC.
- Flux : Authorization Code + PKCE S256.
- Aucun mode secondaire expose aux utilisateurs.

## 2. Pipeline applicatif invariant

Quel que soit le mecanisme d'identite externe, l'application applique toujours le meme pipeline :

1. Recuperer un email verifie depuis l'IdP.
2. Mapper cet email sur BDD_Utilisateurs.
3. Ouvrir une session applicative (identite seulement).
4. Re-resoudre le role a chaque requete cote serveur.
5. Appliquer les controles d'acces (dont ownership).

Invariants :

- BDD_Utilisateurs est l'unique referentiel des roles.
- L'email est la cle de correspondance.
- Les valeurs de droits restent en francais (dont Extention).

## 3. Activation et configuration

Le SSO est operationnel quand ces variables sont coherentes :

- APP_PUBLIC_URL
- OIDC_ISSUER
- OIDC_CLIENT_ID
- OIDC_CLIENT_SECRET (optionnel si client public)

La configuration client IdP doit inclure la callback de l'application.

## 4. Garde-fous de securite

- PKCE S256 obligatoire.
- state/nonce verifies.
- Validation stricte de l'id_token.
- Refus des emails non verifies.
- Messages d'erreur non verbeux.
- En cas d'echec au demarrage du flux SSO : redirection login sans 500.

## 5. Evolution future (si demandee)

Si un second mode devait etre reintroduit, il doit respecter ces regles :

1. Produire uniquement un email verifie.
2. Reutiliser le meme pipeline de mapping et session.
3. Ne pas contourner les dependances d'acces serveur.
4. Conserver les tests de securite (CSRF, acces, ownership, rate limiting).
5. Ne pas introduire de secret en dur.

## 6. Checklist de non-regression

- Lint/typing/tests passent.
- Le callback OIDC couvre succes + echec.
- Le mode client public sans secret est teste.
- Les routes legacy d'auth ne reapparaissent pas.
