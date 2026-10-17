"""Live remote feeds kept in memory and refreshed in the background.

Reads never wait on the network once a feed has loaded: a stale value is returned at once
and refreshed on a background thread (stale-while-revalidate). Only one fetch per feed runs
at a time, and a failed fetch keeps the last good value. A background refresher started
by the API keeps every feed warm, so requests normally never fetch at all.
"""

import logging
import threading
import time
from collections.abc import Callable, Iterable
from typing import Any

log = logging.getLogger(__name__)
RETRY_AFTER = 60  # seconds before an unloaded feed is tried again after a failure


class Feed:
    def __init__(self, name: str, fetch: Callable[[], Any], ttl: float):
        self.name, self.ttl, self._fetch = name, ttl, fetch
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        self._value: Any = None
        self.fetched_at = 0.0
        self._failed_at = 0.0

    @property
    def stale(self) -> bool:
        return time.time() - self.fetched_at >= self.ttl

    def get(self) -> Any:
        """The latest value, or None if the feed has never loaded."""
        if self._value is None:
            if time.time() - self._failed_at >= RETRY_AFTER:
                self.refresh()
        elif self.stale and not self._lock.locked():
            threading.Thread(target=self.refresh, name=f"feed-{self.name}", daemon=True).start()
        return self._value

    def refresh(self, force: bool = False) -> bool:
        """Fetch now unless another thread just did (or `force`). Returns whether a fresh value is held."""
        with self._lock:
            if not force and self._value is not None and not self.stale:
                return True
            try:
                value = self._fetch()
            except Exception as error:  # noqa: BLE001 - any feed failure keeps the last good value
                self._failed_at = time.time()
                log.warning("feed %s: refresh failed: %s", self.name, error)
                return False
            self._value, self.fetched_at = value, time.time()
            return True


def start_refresher(feeds: Iterable[Feed], after: Callable[[], None] | None = None, every: float = 30) -> threading.Event:
    """Load every feed now, then refresh each one whenever it goes stale. `after` runs after each pass.

    Returns an event that is set once the first pass has finished, so startup can wait for it.
    """
    feeds = list(feeds)
    primed = threading.Event()

    def run() -> None:
        while True:
            for feed in feeds:
                if feed.stale:
                    feed.refresh()
            if after:
                try:
                    after()
                except Exception as error:  # noqa: BLE001 - warming is best effort
                    log.warning("feed warm-up failed: %s", error)
            primed.set()
            time.sleep(every)

    threading.Thread(target=run, name="feed-refresher", daemon=True).start()
    return primed
