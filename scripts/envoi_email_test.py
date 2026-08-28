"""Envoi d'un email de test via la configuration SMTP du .env.

Utilisé en développement et à chaque déploiement (checklist sécurité n°13 :
« SMTP vérifié, email de test envoyé »).

Usage : uv run python -m scripts.envoi_email_test
"""

import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    from app.core.config import Settings
    from app.services.notification_service import NotificationService

    settings = Settings()  # pyright: ignore[reportCallIssue]
    service = NotificationService(settings)
    if not service.is_configured:
        logger.error("SMTP non configuré (variables SMTP_* incomplètes dans le .env)")
        return 1

    destinataires = service.admin_recipients or [settings.SMTP_USER]
    ok = service.send(
        destinataires,
        "[FNCCR V2] Email de test",
        "Ceci est un email de test envoyé par l'application FNCCR V2.\n"
        "Si vous le recevez, la configuration SMTP est fonctionnelle.",
    )
    if ok:
        logger.info("Email de test envoyé à %s", ", ".join(destinataires))
        return 0
    logger.error("Échec de l'envoi — voir le détail ci-dessus")
    return 1


if __name__ == "__main__":
    sys.exit(main())
