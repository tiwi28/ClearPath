"""Write the AI "In plain words" summaries for every ward card (data/ward_summaries.json).

Run after ml/09_export_wards.py, or with `make ward-summaries`. Only wards whose numbers (or
the prompt) changed since the last run are sent to Gemini, so a rerun with no new data makes
no calls. Wards are written one at a time and saved as they finish, so a run that hits
Gemini's daily quota (20 requests on the free tier) keeps its progress and the next run picks
up the rest. A ward whose answers keep failing the safety checks is stored as a template
entry and retried on the next run; until then its card shows the template.

Usage: python -m app.write_summaries [--force]
"""

import argparse
import sys
import time
from collections.abc import Callable

from . import ai_summary, wards
from .config import settings

ATTEMPTS = 2       # an unusable answer is retried once; each attempt costs one request of quota
MAX_WAIT = 60      # seconds: wait out a short rate limit, stop on anything longer (a daily quota)
MAX_WAITS = 3


def _summary(values: dict, generate, attempts: int, sleep) -> str | None:
    """A usable summary, or None after `attempts` unusable answers. Raises QuotaExceeded on a long limit."""
    waits = 0
    for _ in range(attempts):
        while True:
            try:
                text = generate(values)
                break
            except ai_summary.QuotaExceeded as error:
                if error.retry_after is None or error.retry_after > MAX_WAIT or waits == MAX_WAITS:
                    raise
                waits += 1  # a short rate limit is not the answer's fault, so it costs no attempt
                sleep(error.retry_after)
        if text:
            return text
    return None


def run(force: bool = False, generate: Callable[[dict], str | None] = ai_summary.generate,
        attempts: int = ATTEMPTS, sleep: Callable[[float], None] = time.sleep) -> dict:
    """Refresh the stored summaries. Returns ward ids written, kept, failed and still pending."""
    data = wards.load()
    store = ai_summary.load_store()
    store.update(model=settings.gemini_model, prompt_version=ai_summary.PROMPT_VERSION, data_version=data.version)
    stored = store.setdefault("wards", {})
    result: dict = {"written": [], "kept": [], "failed": [], "pending": [], "retry_after": None}

    todo = []
    for ward_id in sorted(data.features):
        values = wards.static_facts(data, ward_id)
        current = stored.get(str(ward_id))
        fresh = current and current["source"] == "gemini" and current["facts_hash"] == ai_summary.fingerprint(values)
        if fresh and not force:
            result["kept"].append(ward_id)
        else:
            todo.append((ward_id, values))

    for index, (ward_id, values) in enumerate(todo):
        try:
            text = _summary(values, generate, attempts, sleep)
        except ai_summary.QuotaExceeded as error:
            result["pending"] = [i for i, _ in todo[index:]]
            result["retry_after"] = error.retry_after
            break
        stored[str(ward_id)] = {"facts_hash": ai_summary.fingerprint(values),
                                "source": "gemini" if text else "template", "text": text}
        result["written" if text else "failed"].append(ward_id)
        ai_summary.save_store(store)  # save as we go: a stopped run keeps its progress
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true", help="rewrite every ward, even if its numbers are unchanged")
    args = parser.parse_args()
    if not settings.gemini_api_key.strip():
        print("GEMINI_API_KEY is not set; cards will keep using template summaries.", file=sys.stderr)
        return 1
    result = run(force=args.force)
    print(f"written {len(result['written'])}, unchanged {len(result['kept'])}, "
          f"unusable {len(result['failed'])}, not reached {len(result['pending'])}")
    if result["pending"]:
        wait = f" in about {round(result['retry_after'] / 3600, 1)} h" if result["retry_after"] else " later"
        print(f"Gemini's quota was reached. Run this again{wait} to write wards {', '.join(map(str, result['pending']))}.")
    if result["failed"]:
        print(f"Wards {', '.join(map(str, result['failed']))} show the template; run again to retry them.")
    return 0 if not (result["pending"] or result["failed"]) else 1


if __name__ == "__main__":
    sys.exit(main())
