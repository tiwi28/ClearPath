import threading
import time

from app import feeds
from app.feeds import Feed


def counting(value="v", fail=False, wait: threading.Event | None = None):
    calls = []

    def fetch():
        calls.append(1)
        if wait:
            wait.wait(2)
        if fail:
            raise ValueError("down")
        return f"{value}{len(calls)}"
    return fetch, calls


def test_first_read_loads_and_later_reads_do_not_fetch():
    fetch, calls = counting()
    feed = Feed("t", fetch, ttl=60)
    assert feed.get() == "v1" and feed.get() == "v1" and len(calls) == 1


def test_a_feed_that_never_loaded_returns_none_and_backs_off():
    fetch, calls = counting(fail=True)
    feed = Feed("t", fetch, ttl=60)
    assert feed.get() is None and feed.get() is None
    assert len(calls) == 1  # the second read did not retry within RETRY_AFTER


def test_a_failed_refresh_keeps_the_last_good_value():
    state = {"fail": False}

    def fetch():
        if state["fail"]:
            raise ValueError("down")
        return "good"
    feed = Feed("t", fetch, ttl=60)
    feed.get()
    feed.fetched_at = 0  # stale
    state["fail"] = True
    assert feed.refresh() is False and feed.get() == "good"


def test_a_stale_read_returns_at_once_and_refreshes_in_the_background():
    release = threading.Event()
    fetch, calls = counting()
    feed = Feed("t", fetch, ttl=60)
    feed.get()
    feed.fetched_at = 0
    feed._fetch = lambda: (release.wait(2), "new")[1]
    started = time.time()
    assert feed.get() == "v1" and time.time() - started < 0.5
    release.set()
    for _ in range(50):
        if feed.get() == "new":
            break
        time.sleep(0.02)
    assert feed.get() == "new"


def test_concurrent_first_reads_fetch_once():
    release = threading.Event()
    fetch, calls = counting(wait=release)
    feed = Feed("t", fetch, ttl=60)
    results = []
    threads = [threading.Thread(target=lambda: results.append(feed.get())) for _ in range(5)]
    for thread in threads:
        thread.start()
    time.sleep(0.1)
    release.set()
    for thread in threads:
        thread.join(2)
    assert results == ["v1"] * 5 and len(calls) == 1


def test_refresher_loads_every_feed_and_runs_the_warm_up():
    a, b = Feed("a", lambda: 1, ttl=60), Feed("b", lambda: 2, ttl=60)
    warmed = threading.Event()
    primed = feeds.start_refresher([a, b], after=warmed.set, every=60)
    assert primed.wait(2) and warmed.is_set()
    assert (a.get(), b.get()) == (1, 2)
