from psycopg_pool import ConnectionPool

from .config import settings

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    """Lazy pool so the API still boots (on mocks) without a database."""
    global _pool
    if _pool is None:
        _pool = ConnectionPool(settings.database_url, min_size=1, max_size=5, open=True)
    return _pool
