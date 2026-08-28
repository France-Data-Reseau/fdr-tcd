# Guide de l'administrateur — Cartographie des Usages TCD (FNCCR)

> Pour les administrateurs FNCCR de la plateforme. Explique comment gérer les
> accès et les droits des utilisateurs. Aucune compétence technique requise.

---

## 1. Votre rôle

En tant qu'administrateur, vous **décidez qui peut accéder à la plateforme et
avec quels droits**. Concrètement :
- vous **attribuez les droits** (Administrateur, Éditeur, Visiteur) aux
  utilisateurs ;
- vous **rattachez** chaque utilisateur à sa collectivité ;
- vous **validez** les comptes en attente.

## 2. Se connecter

1. Ouvrez l'adresse de la plateforme dans votre navigateur.
2. Cliquez sur **« Se connecter avec France Data Réseau »**.
3. Saisissez vos identifiants France Data Réseau (les mêmes que pour Grist).
4. Vous arrivez sur l'accueil ; comme vous êtes administrateur, vous voyez en
   plus le bouton **« Console Administrateur »**.

> La plateforme ne gère **pas** de mot de passe : la connexion passe entièrement
> par France Data Réseau (SSO). Il n'y a donc **rien à retenir de plus** que votre
> compte France Data Réseau.

## 3. La console administrateur

Depuis l'accueil → **Console Administrateur**. Vous y voyez la **liste des
utilisateurs** ; pour chacun, deux réglages, **enregistrés immédiatement** :

| Réglage | À quoi ça sert |
|---|---|
| **Droits** | le niveau d'accès de la personne (voir §4) |
| **Collectivité** | la collectivité que la personne a le droit de modifier |

Pour modifier : choisissez la nouvelle valeur dans la liste déroulante — c'est
pris en compte tout de suite.

## 4. Les 4 niveaux de droits

| Droit | Ce que la personne peut faire |
|---|---|
| **Administrateur** | tout, y compris gérer les droits des autres |
| **Éditeur** | consulter la carte **et** saisir/modifier les données de **sa** collectivité |
| **Visiteur** | consulter la carte uniquement (lecture seule) |
| **En attente** | rien encore — le compte doit être validé par un admin |

## 5. Ajouter un nouvel utilisateur

L'ajout se fait en **deux temps** (avec **le même email** des deux côtés) :

1. **Côté France Data Réseau** : la personne doit avoir un **compte France Data
   Réseau** (c'est ce qui lui permet de se connecter). Si elle n'en a pas, il
   faut le demander à France Data Réseau.
2. **Côté plateforme** : vous créez sa ligne dans la base des utilisateurs
   (aujourd'hui dans **Grist**, table `BDD_Utilisateurs`), avec son email, son
   nom, son droit et sa collectivité.

> Pourquoi deux endroits ? France Data Réseau gère **l'identité** (qui vous êtes),
> la plateforme gère **les droits métier** (ce que vous avez le droit de faire).
> Une personne qui a un compte France Data Réseau mais **pas** de ligne dans la
> base se verra **refuser l'accès** — c'est voulu (liste fermée).

## 6. Valider un compte « En attente »

Un utilisateur en droit **« En attente »** ne peut pas encore accéder. Pour lui
ouvrir l'accès : dans la console, passez son droit à **Éditeur** (ou Visiteur) et
choisissez sa **collectivité de rattachement**.

## 7. Bon à savoir

- **Chaque éditeur ne peut modifier que SA collectivité.** La plateforme empêche
  automatiquement quelqu'un de modifier une autre collectivité (sécurité).
- Les **listes de choix** (statuts, thèmes, connectivités, solutions…) et les
  données de référence sont gérées dans **Grist** — pas besoin de toucher au code
  pour les faire évoluer.
- En cas de doute ou de blocage d'un utilisateur, vérifiez d'abord : (a) a-t-il un
  compte France Data Réseau ? (b) a-t-il une ligne dans `BDD_Utilisateurs` avec le
  **même email** et un droit ≠ « En attente » ?
