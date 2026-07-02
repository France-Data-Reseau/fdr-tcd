"""Envoi d'emails (SMTP) : magic links et notifications administrateur.

- DORMANT si les variables SMTP_* sont incomplètes (développement) : les
  fonctions journalisent et ne font rien — jamais d'exception vers l'appelant.
- En production, la complétude du SMTP est imposée au démarrage (config.py) :
  le magic link est le seul moyen de connexion.
- Les échecs d'envoi sont journalisés SANS le contenu du message (un magic
  link est un secret) et ne produisent jamais de 500 côté utilisateur.
"""

import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import Settings

logger = logging.getLogger(__name__)


class NotificationService:
    def __init__(self, settings: Settings):
        self._settings = settings

    @property
    def is_configured(self) -> bool:
        s = self._settings
        return bool(s.SMTP_HOST and s.SMTP_USER and s.SMTP_PASSWORD)

    @property
    def admin_recipients(self) -> list[str]:
        return [
            a.strip()
            for a in self._settings.ADMIN_NOTIFY_EMAILS.split(",")
            if a.strip()
        ]

    def send(self, recipients: list[str], subject: str, body: str) -> bool:
        """Envoi synchrone (appeler via asyncio.to_thread depuis les routes).

        Retourne False en cas d'échec — ne lève jamais.
        """
        if not self.is_configured:
            logger.info("SMTP non configuré — email non envoyé (%s)", subject)
            return False
        s = self._settings
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = s.SMTP_FROM or s.SMTP_USER
        message["To"] = ", ".join(recipients)
        message.set_content(body)
        contexte = ssl.create_default_context()
        try:
            if s.SMTP_PORT == 465:
                with smtplib.SMTP_SSL(s.SMTP_HOST, s.SMTP_PORT, context=contexte,
                                      timeout=15) as serveur:
                    serveur.login(s.SMTP_USER, s.SMTP_PASSWORD)
                    serveur.send_message(message)
            else:
                with smtplib.SMTP(s.SMTP_HOST, s.SMTP_PORT, timeout=15) as serveur:
                    serveur.ehlo()
                    serveur.starttls(context=contexte)
                    serveur.login(s.SMTP_USER, s.SMTP_PASSWORD)
                    serveur.send_message(message)
            return True
        except smtplib.SMTPAuthenticationError as exc:
            # Cas Microsoft 365 : auth basique désactivée → code 535
            logger.error("SMTP : authentification refusée (%s)", exc.smtp_code)
            return False
        except (smtplib.SMTPException, OSError) as exc:
            logger.error("SMTP : échec d'envoi (%s)", type(exc).__name__)
            return False

    # --- Emails métier ---

    def send_magic_link(self, email: str, lien: str, ttl_minutes: int) -> bool:
        """Envoie le lien de connexion. Le lien n'est jamais journalisé."""
        corps = (
            "Bonjour,\n\n"
            "Voici votre lien de connexion à la Cartographie des Usages TCD "
            "des Collectivités (FNCCR) :\n\n"
            f"{lien}\n\n"
            f"Ce lien est valable {ttl_minutes} minutes et ne peut être utilisé "
            "qu'une seule fois.\n"
            "Si vous n'êtes pas à l'origine de cette demande, ignorez cet email.\n"
        )
        return self.send([email], "[FNCCR] Votre lien de connexion", corps)

    def notify_new_collectivite(self, nom: str, createur: str, email: str) -> bool:
        """Notifie les admins qu'un Éditeur a créé une collectivité à valider."""
        recipients = self.admin_recipients
        if not recipients:
            return False
        corps = (
            "Une nouvelle collectivité a été créée sur l'application FNCCR.\n\n"
            f"Collectivité : {nom}\n"
            f"Créée par    : {createur or '(inconnu)'} <{email}>\n\n"
            "À vérifier, et à rattacher à son créateur si pertinent, dans la "
            "console administrateur :\n"
            f"{self._settings.APP_PUBLIC_URL}/admin\n"
        )
        return self.send(
            recipients, f"[FNCCR] Nouvelle collectivité à valider — {nom}", corps
        )

    def notify_new_user(self, prenom: str, nom: str, email: str,
                        organisation: str, collectivite: str) -> bool:
        """Notifie les administrateurs d'une nouvelle demande d'accès."""
        recipients = self.admin_recipients
        if not recipients:
            logger.info("Pas de destinataires admin — notification non envoyée")
            return False
        nom_complet = " ".join(p for p in (prenom, nom) if p).strip() or "(sans nom)"
        corps = (
            "Une nouvelle demande d'accès a été déposée sur l'application FNCCR.\n\n"
            f"Nom          : {nom_complet}\n"
            f"Email        : {email}\n"
            f"Collectivité : {collectivite or '(non renseignée)'}\n"
            f"Organisation : {organisation or '(non renseignée)'}\n\n"
            "Statut : En attente — à valider dans la console administrateur :\n"
            f"{self._settings.APP_PUBLIC_URL}/admin\n"
        )
        return self.send(
            recipients, f"[FNCCR] Nouvelle demande d'accès — {nom_complet}", corps
        )
