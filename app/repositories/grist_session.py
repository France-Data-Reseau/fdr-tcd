"""Fabrique du client pygrister partagé.

Seul endroit de l'application où vivent la clé API et l'URL du serveur Grist.
Les erreurs remontées plus haut (base.py) sont reformulées sans doc ID ni URL.

- timeout global (connect, read) via ``request_options`` ;
- retries bornés sur les GET uniquement (les écritures ne sont pas idempotentes) ;
- ``pool_maxsize`` dimensionné pour les lectures parallèles de la restitution ;
- ``GRIST_RAISE_ERROR='N'`` : les status HTTP sont vérifiés par ``base.py``,
  qui produit des erreurs sobres (jamais de stacktrace utilisateur).
"""

from pygrister.api import GristApi
from pygrister.apicaller import ApiCaller
from pygrister.config import Configurator
from requests import Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.core.config import Settings


def build_grist_api(settings: Settings) -> GristApi:
    """Construit le client Grist configuré pour l'instance self-managed FDR."""
    configurator = Configurator(
        config={
            "GRIST_API_KEY": settings.GRIST_API_KEY,
            "GRIST_DOC_ID": settings.GRIST_DOC_ID,
            "GRIST_SELF_MANAGED": "Y",
            "GRIST_SELF_MANAGED_HOME": settings.GRIST_SERVER_URL,
            "GRIST_SELF_MANAGED_SINGLE_ORG": "Y",
            "GRIST_RAISE_ERROR": "N",
        }
    )
    caller = ApiCaller(
        configurator,
        request_options={
            "timeout": (settings.GRIST_TIMEOUT_CONNECT, settings.GRIST_TIMEOUT_READ)
        },
    )
    caller.session = _build_session(settings)
    return GristApi(custom_apicaller=caller)


def _build_session(settings: Settings) -> Session:
    session = Session()
    retry = Retry(
        total=settings.GRIST_RETRIES,
        backoff_factor=0.5,
        status_forcelist=(502, 503, 504),
        allowed_methods=frozenset({"GET"}),
    )
    # pool_block=True : borne DURE sur la concurrence sortante vers Grist —
    # si Grist ralentit, les threads excédentaires ATTENDENT une connexion du
    # pool (jusqu'au timeout) au lieu d'empiler des connexions et d'écrouler
    # l'app en cascade (revue : « deadly embrace »).
    adapter = HTTPAdapter(
        max_retries=retry, pool_maxsize=8, pool_block=True
    )
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session
