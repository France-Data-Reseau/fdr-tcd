"""Magic links : jetons de connexion signés, à usage unique réel.

Conception (voir 02_AUTHENTIFICATION.md) :
- jeton signé itsdangerous avec un SALT DÉDIÉ (distinct des sessions),
  TTL court, lié à l'email ;
- usage unique garanti par un magasin mémoire des jetons consommés
  (invariant mono-worker) ;
- chaque jeton embarque le boot-id du processus : un redémarrage invalide
  tous les jetons antérieurs (pas de fenêtre de rejeu post-redémarrage) ;
- l'URL du lien est construite EXCLUSIVEMENT depuis APP_PUBLIC_URL — jamais
  depuis le header Host (anti-empoisonnement) ;
- rate limit par email ciblé (anti mail-bombing), en plus du par-IP slowapi.
"""

import secrets
import threading
import time
from collections.abc import Callable

from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.core.config import Settings

_SALT = "fnccr-magic-link-v2"


class EmailRateLimiter:
    """Limite le nombre d'envois par adresse email sur une fenêtre glissante.

    Thread-safe : lecture-modification-écriture sous verrou (threadpool FastAPI).
    """

    def __init__(self, max_envois: int = 3, fenetre_secondes: int = 900,
                 clock: Callable[[], float] = time.monotonic):
        self._max = max_envois
        self._fenetre = fenetre_secondes
        self._clock = clock
        self._envois: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, email: str) -> bool:
        cle = email.strip().lower()
        maintenant = self._clock()
        with self._lock:
            horodatages = [
                t for t in self._envois.get(cle, []) if maintenant - t < self._fenetre
            ]
            if len(horodatages) >= self._max:
                self._envois[cle] = horodatages
                return False
            horodatages.append(maintenant)
            self._envois[cle] = horodatages
            return True


class MagicLinkService:
    def __init__(self, settings: Settings, boot_id: str | None = None):
        self._serializer = URLSafeTimedSerializer(settings.SECRET_KEY, salt=_SALT)
        self._ttl = settings.MAGIC_LINK_TTL_SECONDS
        self._base_url = settings.APP_PUBLIC_URL.rstrip("/")
        # boot-id : invalide tous les jetons émis avant le démarrage du processus
        self._boot_id = boot_id or secrets.token_urlsafe(8)
        self._consumed: set[str] = set()
        # Anti-TOCTOU : la vérification « déjà consommé ? » et la consommation
        # doivent être ATOMIQUES (deux requêtes simultanées avec le même lien)
        self._lock = threading.Lock()

    @property
    def ttl_minutes(self) -> int:
        return max(1, self._ttl // 60)

    def generate_url(self, email: str) -> str:
        """Construit le lien de connexion (URL bâtie sur APP_PUBLIC_URL)."""
        jeton_id = secrets.token_urlsafe(8)
        token = self._serializer.dumps(
            {"email": email.strip().lower(), "jti": jeton_id, "boot": self._boot_id}
        )
        return f"{self._base_url}/auth/verifier?token={token}"

    def peek_valid(self, token: str) -> bool:
        """Validité SANS consommer (page de confirmation GET).

        Un jeton déjà consommé est considéré invalide — la page de
        confirmation ne réapparaît pas après usage.
        """
        payload = self._decode(token)
        if payload is None:
            return False
        with self._lock:
            return payload["jti"] not in self._consumed

    def verify_and_consume(self, token: str) -> str | None:
        """Vérifie puis consomme le jeton. Retourne l'email, ou None.

        Un jeton expiré, falsifié, d'un démarrage précédent ou déjà consommé
        est refusé — sans distinction du motif (réponse neutre).
        """
        payload = self._decode(token)
        if payload is None:
            return None
        with self._lock:
            if payload["jti"] in self._consumed:
                return None
            self._consumed.add(payload["jti"])
        return payload["email"]

    def _decode(self, token: str) -> dict | None:
        if not token:
            return None
        try:
            payload = self._serializer.loads(token, max_age=self._ttl)
        except BadSignature:  # englobe SignatureExpired
            return None
        if not isinstance(payload, dict) or payload.get("boot") != self._boot_id:
            return None
        if not payload.get("email") or not payload.get("jti"):
            return None
        return payload
