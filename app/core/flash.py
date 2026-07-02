"""Messages flash en session (succès vert / erreur rouge, comme la v1).

La session vit dans un cookie signé (~4 Ko max) : nombre et taille des
messages bornés pour ne jamais dépasser la limite.
"""

from fastapi import Request

_MAX_MESSAGES = 5
_MAX_LONGUEUR = 300


def flash(request: Request, message: str, category: str = "success") -> None:
    messages = request.session.get("flash", [])
    messages.append({"message": message[:_MAX_LONGUEUR], "category": category})
    request.session["flash"] = messages[-_MAX_MESSAGES:]


def get_flashed_messages(request: Request) -> list[dict]:
    return request.session.pop("flash", [])
