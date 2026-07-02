"""Magic links : usage unique réel, boot-id, falsification, rate limit email."""

from app.core.config import Settings
from app.services.magic_link_service import EmailRateLimiter, MagicLinkService

BASE = {
    "GRIST_API_KEY": "cle",
    "GRIST_DOC_ID": "doc",
    "GRIST_SERVER_URL": "https://grist.exemple.test",
    "SECRET_KEY": "s" * 32,
    "APP_PUBLIC_URL": "https://fdr2.exemple.test",
}


def make_settings(**kwargs) -> Settings:
    return Settings(_env_file=None, **{**BASE, **kwargs})  # pyright: ignore[reportCallIssue]


def test_url_construite_sur_app_public_url():
    service = MagicLinkService(make_settings())
    url = service.generate_url("victor@exemple.fr")
    assert url.startswith("https://fdr2.exemple.test/auth/verifier?token=")


def test_verification_et_consommation():
    service = MagicLinkService(make_settings())
    token = service.generate_url("Victor@Exemple.fr").split("token=", 1)[1]
    assert service.peek_valid(token)
    assert service.verify_and_consume(token) == "victor@exemple.fr"


def test_jeton_rejoue_refuse():
    service = MagicLinkService(make_settings())
    token = service.generate_url("victor@exemple.fr").split("token=", 1)[1]
    assert service.verify_and_consume(token) is not None
    assert service.verify_and_consume(token) is None  # déjà consommé


def test_peek_ne_consomme_pas():
    service = MagicLinkService(make_settings())
    token = service.generate_url("victor@exemple.fr").split("token=", 1)[1]
    assert service.peek_valid(token)
    assert service.peek_valid(token)  # toujours valide : GET sans effet de bord
    assert service.verify_and_consume(token) is not None


def test_jeton_d_un_demarrage_precedent_refuse():
    settings = make_settings()
    ancien = MagicLinkService(settings, boot_id="boot-precedent")
    token = ancien.generate_url("victor@exemple.fr").split("token=", 1)[1]
    nouveau = MagicLinkService(settings, boot_id="boot-courant")
    assert not nouveau.peek_valid(token)
    assert nouveau.verify_and_consume(token) is None


def test_jeton_falsifie_refuse():
    service = MagicLinkService(make_settings())
    token = service.generate_url("victor@exemple.fr").split("token=", 1)[1]
    falsifie = token[:-4] + "XXXX"
    assert not service.peek_valid(falsifie)
    assert service.verify_and_consume(falsifie) is None
    assert service.verify_and_consume("") is None


def test_jeton_expire_refuse():
    # TTL négatif : tout jeton est expiré dès son émission
    service = MagicLinkService(make_settings(MAGIC_LINK_TTL_SECONDS=-1))
    token = service.generate_url("victor@exemple.fr").split("token=", 1)[1]
    assert service.verify_and_consume(token) is None


def test_secret_different_refuse():
    token = (
        MagicLinkService(make_settings())
        .generate_url("victor@exemple.fr")
        .split("token=", 1)[1]
    )
    autre = MagicLinkService(make_settings(SECRET_KEY="a" * 32))
    assert autre.verify_and_consume(token) is None


def test_consommation_concurrente_un_seul_gagnant():
    """Anti-TOCTOU (revue 2026-06-13) : deux requêtes simultanées avec le
    même lien → le jeton n'est consommé qu'UNE seule fois."""
    from concurrent.futures import ThreadPoolExecutor

    service = MagicLinkService(make_settings())
    token = service.generate_url("victor@exemple.fr").split("token=", 1)[1]
    with ThreadPoolExecutor(max_workers=8) as pool:
        resultats = list(pool.map(
            lambda _: service.verify_and_consume(token), range(50)
        ))
    succes = [r for r in resultats if r is not None]
    assert len(succes) == 1


def test_rate_limit_par_email():
    class FausseHorloge:
        t = 0.0

        def __call__(self):
            return self.t

    horloge = FausseHorloge()
    limiteur = EmailRateLimiter(max_envois=3, fenetre_secondes=900, clock=horloge)
    for _ in range(3):
        assert limiteur.allow("victime@exemple.fr")
    assert not limiteur.allow("victime@exemple.fr")
    assert limiteur.allow("autre@exemple.fr")  # indépendant par email
    horloge.t = 901
    assert limiteur.allow("victime@exemple.fr")  # fenêtre glissée
