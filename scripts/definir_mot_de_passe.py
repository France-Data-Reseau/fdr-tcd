"""Définit (ou réinitialise) le mot de passe d'un compte — utilitaire admin.

Sert à initialiser les comptes existants (sans hash) et à dépanner un oubli,
tant qu'il n'y a pas de reset par email (SMTP en panne). Le mot de passe est
demandé en INTERACTIF (jamais en argument, pour ne pas le laisser dans
l'historique du shell) et validé contre la politique de robustesse.

Usage (sur le VPS, terminal interactif) :
    docker compose exec fdr2 python -m scripts.definir_mot_de_passe prenom.nom@exemple.fr
"""

import getpass
import sys

from app.services.password_service import password_errors


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage : python -m scripts.definir_mot_de_passe <email>")
        return 2
    email = argv[1].strip()

    from app.dependencies import get_auth_service, get_utilisateur_repository

    utilisateur = get_utilisateur_repository().get_by_email(email)
    if utilisateur is None:
        print(f"Aucun compte pour l'adresse « {email} ».")
        return 1

    qui = f"{utilisateur.get('prenom', '')} {utilisateur.get('nom', '')}".strip()
    print(f"Compte : {qui or '(sans nom)'} — droits : {utilisateur.get('droits', '')}")
    mot_de_passe = getpass.getpass("Nouveau mot de passe : ")
    confirmation = getpass.getpass("Confirmer le mot de passe : ")
    if mot_de_passe != confirmation:
        print("Les mots de passe ne correspondent pas.")
        return 1
    erreurs = password_errors(mot_de_passe)
    if erreurs:
        print("Mot de passe refusé — il doit comporter " + ", ".join(erreurs) + ".")
        return 1

    get_auth_service().set_password(utilisateur["id"], mot_de_passe)
    print(f"Mot de passe défini pour « {email} ».")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
