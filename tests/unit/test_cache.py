"""Cache TTL : expiration, invalidation ciblée."""

from app.repositories.cache import TableCache


class FausseHorloge:
    def __init__(self):
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def avancer(self, secondes: float) -> None:
        self.t += secondes


def test_get_avant_expiration():
    horloge = FausseHorloge()
    cache = TableCache(ttl_seconds=300, clock=horloge)
    cache.set("T", [{"id": 1}])
    horloge.avancer(299)
    assert cache.get("T") == [{"id": 1}]


def test_get_apres_expiration():
    horloge = FausseHorloge()
    cache = TableCache(ttl_seconds=300, clock=horloge)
    cache.set("T", [{"id": 1}])
    horloge.avancer(300)
    assert cache.get("T") is None


def test_invalidation_ciblee():
    cache = TableCache(ttl_seconds=300)
    cache.set("A", [{"id": 1}])
    cache.set("B", [{"id": 2}])
    cache.invalidate("A")
    assert cache.get("A") is None
    assert cache.get("B") == [{"id": 2}]


def test_table_inconnue():
    cache = TableCache(ttl_seconds=300)
    assert cache.get("inconnue") is None
    cache.invalidate("inconnue")  # ne lève pas


def test_eviction_au_dela_du_maximum():
    cache = TableCache(ttl_seconds=300, max_entries=2)
    cache.set("A", [{"id": 1}])
    cache.set("B", [{"id": 2}])
    cache.set("C", [{"id": 3}])  # évince A (le plus ancien)
    assert cache.get("A") is None
    assert cache.get("B") == [{"id": 2}]
    assert cache.get("C") == [{"id": 3}]


def test_invalidation_totale():
    cache = TableCache(ttl_seconds=300)
    cache.set("A", [{"id": 1}])
    cache.set("B", [{"id": 2}])
    cache.invalidate_all()
    assert cache.get("A") is None
    assert cache.get("B") is None


def test_acces_concurrents_sans_erreur():
    """Thread-safety (revue 2026-06-13) : set/get/invalidate concurrents avec
    éviction active ne lèvent ni RuntimeError ni KeyError."""
    from concurrent.futures import ThreadPoolExecutor

    cache = TableCache(ttl_seconds=300, max_entries=4)

    def marteler(graine: int) -> None:
        for i in range(300):
            cle = f"T{(graine * 7 + i) % 10}"
            cache.set(cle, [{"id": i}])
            cache.get(cle)
            if i % 3 == 0:
                cache.invalidate(cle)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(marteler, range(8)))  # propage toute exception
