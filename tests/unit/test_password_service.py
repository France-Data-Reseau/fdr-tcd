"""Service mot de passe : hachage argon2id et politique de robustesse."""

from app.services.password_service import (
    hash_password,
    is_strong,
    password_errors,
    verify_dummy,
    verify_password,
)


def test_hash_et_verify():
    h = hash_password("MaPhraseDePasse-2026")
    assert h != "MaPhraseDePasse-2026"  # jamais en clair
    assert h.startswith("$argon2id$")
    assert verify_password(h, "MaPhraseDePasse-2026")
    assert not verify_password(h, "mauvais")


def test_hash_sale_unique():
    # Deux hachages du même mot de passe diffèrent (salt aléatoire)
    assert hash_password("meme-mdp-12345") != hash_password("meme-mdp-12345")


def test_verify_hash_invalide_ne_leve_pas():
    assert verify_password("pas-un-hash-argon2", "x") is False


def test_verify_dummy_ne_leve_jamais():
    verify_dummy("n'importe quoi")  # ne doit pas lever


def test_politique_longueur():
    assert "12 caractères" in " ".join(password_errors("court"))
    assert password_errors("a" * 12) == []  # 12 caractères suffit
    assert is_strong("PhraseDePasseLongue-2026")


def test_politique_mot_de_passe_commun():
    # Présent dans la liste des communs malgré ≥ 12 caractères
    assert not is_strong("motdepasse123")
    assert "courant" in " ".join(password_errors("motdepasse123"))
