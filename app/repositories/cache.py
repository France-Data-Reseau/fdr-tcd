"""Cache TTL en mémoire des tables Grist.

Invariant mono-worker (voir AGENTS.md) : ce cache vit dans le processus unique
de l'application. L'invalidation est déclenchée par les méthodes d'écriture de
``base.py`` — jamais par les services.

Thread-safety : les routes synchrones tournent dans le threadpool FastAPI —
toutes les opérations sont protégées par un verrou d'instance (revue du
2026-06-13 : éviction pendant itération, double expiration TTL).
"""

import threading
import time
from collections.abc import Callable


class TableCache:
    """Cache par table : ``get``/``set``/``invalidate``, TTL en secondes.

    ``max_entries`` borne le nombre d'entrées (12 tables + clés de choix :
    largement en dessous en usage normal) — garde-fou contre une dérive
    mémoire si des clés dynamiques étaient introduites par erreur.
    """

    def __init__(
        self,
        ttl_seconds: int = 300,
        clock: Callable[[], float] = time.monotonic,
        max_entries: int = 64,
    ):
        self._ttl = ttl_seconds
        self._clock = clock
        self._max_entries = max_entries
        self._entries: dict[str, tuple[float, list[dict]]] = {}
        self._lock = threading.Lock()

    def get(self, table_id: str) -> list[dict] | None:
        with self._lock:
            entry = self._entries.get(table_id)
            if entry is None:
                return None
            stored_at, records = entry
            if self._clock() - stored_at >= self._ttl:
                self._entries.pop(table_id, None)
                return None
            return records

    def set(self, table_id: str, records: list[dict]) -> None:
        with self._lock:
            if (
                table_id not in self._entries
                and len(self._entries) >= self._max_entries
            ):
                # Éviction de l'entrée la plus ancienne (insertion ordonnée)
                self._entries.pop(next(iter(self._entries)))
            self._entries[table_id] = (self._clock(), records)

    def invalidate(self, table_id: str) -> None:
        with self._lock:
            self._entries.pop(table_id, None)

    def invalidate_all(self) -> None:
        with self._lock:
            self._entries.clear()
