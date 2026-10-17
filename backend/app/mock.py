import json
from pathlib import Path

MOCK_DIR = Path(__file__).parent / "mock"


def load(name: str) -> dict:
    return json.loads((MOCK_DIR / name).read_text())
