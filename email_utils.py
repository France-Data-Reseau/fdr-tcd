"""
Envoi d'emails de notification (SMTP).

Conçu pour être DORMANT tant que le SMTP n'est pas configuré : si les variables
d'environnement SMTP_* / ADMIN_NOTIFY_EMAILS ne sont pas définies, les fonctions
ne font rien (et journalisent l'info). L'inscription n'est jamais bloquée par un
problème d'email — les erreurs d'envoi sont attrapées et loguées.

Pour ACTIVER, ajouter au .env (exemple Gmail) :
    SMTP_HOST=smtp.gmail.com
    SMTP_PORT=587
    SMTP_USER=vwelschinger@gmail.com
    SMTP_PASSWORD=<mot de passe d'application Google, 16 caractères>
    SMTP_FROM=vwelschinger@gmail.com          # optionnel (défaut = SMTP_USER)
    ADMIN_NOTIFY_EMAILS=vwelschinger@gmail.com  # destinataires, séparés par des virgules
    APP_PUBLIC_URL=https://fdr.revorun.eu       # optionnel (lien dans l'email)
"""

import os
import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage

logger = logging.getLogger("email_utils")


def _config() -> dict | None:
    """Retourne la config SMTP si elle est complète, sinon None (mode dormant)."""
    host = os.getenv("SMTP_HOST", "").strip()
    user = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASSWORD", "").strip()
    recipients = [
        a.strip()
        for a in os.getenv("ADMIN_NOTIFY_EMAILS", "").split(",")
        if a.strip()
    ]
    if not (host and user and password and recipients):
        return None
    return {
        "host": host,
        "port": int(os.getenv("SMTP_PORT", "587") or "587"),
        "user": user,
        "password": password,
        "from": os.getenv("SMTP_FROM", "").strip() or user,
        "recipients": recipients,
    }


def is_configured() -> bool:
    """Vrai si l'envoi d'email est activé (SMTP configuré)."""
    return _config() is not None


def _send_sync(cfg: dict, subject: str, body: str) -> None:
    """Envoi SMTP bloquant (à appeler dans un thread)."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg["from"]
    msg["To"] = ", ".join(cfg["recipients"])
    msg.set_content(body)

    context = ssl.create_default_context()
    if cfg["port"] == 465:
        with smtplib.SMTP_SSL(cfg["host"], cfg["port"], context=context, timeout=15) as server:
            server.login(cfg["user"], cfg["password"])
            server.send_message(msg)
    else:
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=15) as server:
            server.ehlo()
            server.starttls(context=context)
            server.login(cfg["user"], cfg["password"])
            server.send_message(msg)


async def notify_new_user(
    prenom: str,
    nom: str,
    email: str,
    organisation: str = "",
    collectivite: str = "",
) -> None:
    """
    Notifie les administrateurs qu'un nouvel utilisateur a demandé un accès.
    Ne lève jamais d'exception (échec silencieux journalisé).
    """
    cfg = _config()
    if cfg is None:
        logger.info(
            "Notification d'inscription non envoyée (SMTP non configuré) — %s %s <%s>",
            prenom, nom, email,
        )
        return

    nom_complet = " ".join(p for p in (prenom, nom) if p).strip() or "(sans nom)"
    subject = f"[FNCCR] Nouvelle demande d'accès — {nom_complet}"
    lignes = [
        "Une nouvelle demande d'accès vient d'être déposée sur l'application FNCCR.",
        "",
        f"Nom        : {nom_complet}",
        f"Email      : {email}",
        f"Collectivité : {collectivite or '(non renseignée)'}",
        f"Organisation : {organisation or '(non renseignée)'}",
        "",
        "Statut : En attente — à valider dans la table BDD_Utilisateurs (Grist).",
    ]
    public_url = os.getenv("APP_PUBLIC_URL", "").strip()
    if public_url:
        lignes += ["", f"Application : {public_url}"]
    body = "\n".join(lignes)

    try:
        await asyncio.to_thread(_send_sync, cfg, subject, body)
        logger.info("Notification d'inscription envoyée à %s", ", ".join(cfg["recipients"]))
    except Exception as e:
        logger.error("Échec d'envoi de la notification d'inscription : %s", e)
