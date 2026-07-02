"""Mots de passe : hachage argon2id et politique de robustesse.

Le hash ne sort JAMAIS de cette couche vers les logs, l'API, les templates ou
les messages d'erreur (même règle que la clé API Grist).

Politique « mot de passe fort » (NIST 2024 : la longueur prime sur les règles
de composition arbitraires) : au moins 12 caractères, et refus d'une liste de
mots de passe très communs.
"""

import argon2
from argon2.exceptions import (
    InvalidHashError,
    VerificationError,
    VerifyMismatchError,
)

# Paramètres OWASP par défaut d'argon2id (time_cost=3, memory_cost=64 MiB,
# parallelism=4) — adaptés à un login occasionnel sur un conteneur mono-worker.
_hasher = argon2.PasswordHasher()

# Hash factice pré-calculé : `verify_dummy` consomme un temps comparable à une
# vraie vérification, pour ne pas révéler par timing qu'un email est inconnu.
_DUMMY_HASH = _hasher.hash("xxxxxxxxxxxxxxxx")

LONGUEUR_MIN = 12

# Mots de passe très communs refusés (formes minuscules). La longueur minimale
# élimine déjà l'essentiel des classiques courts ; cette liste vise les
# variantes longues fréquentes.
_MOTS_DE_PASSE_COMMUNS = frozenset({
    "password1234", "motdepasse123", "motdepasse1234", "azertyuiop123",
    "azertyuiop1234", "qwertyuiop123", "qwertyui012345", "123456789012",
    "1234567890123", "0123456789012", "password12345", "passw0rd1234",
    "administrateur", "administrator1", "motdepassefort", "changemoi1234",
    "bienvenue1234", "soleil12345678", "iloveyou12345", "loveyou123456",
})


def hash_password(password: str) -> str:
    """Hash argon2id (salt généré automatiquement, intégré au hash)."""
    return _hasher.hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    """Vérifie un mot de passe contre son hash. False si non concordant ou
    hash invalide — jamais d'exception remontée."""
    try:
        _hasher.verify(stored_hash, password)
        return True
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def verify_dummy(password: str) -> None:
    """Consomme un temps de vérification sur le hash factice (anti-timing) :
    à appeler quand l'email n'existe pas ou n'a pas de hash, pour que la durée
    de réponse ne trahisse pas l'existence du compte."""
    try:
        _hasher.verify(_DUMMY_HASH, password)
    except Exception:
        pass


def password_errors(password: str) -> list[str]:
    """Raisons pour lesquelles le mot de passe est refusé (vide = accepté)."""
    erreurs: list[str] = []
    if len(password) < LONGUEUR_MIN:
        erreurs.append(f"au moins {LONGUEUR_MIN} caractères")
    if password.lower() in _MOTS_DE_PASSE_COMMUNS:
        erreurs.append("un mot de passe moins courant")
    return erreurs


def is_strong(password: str) -> bool:
    return not password_errors(password)
