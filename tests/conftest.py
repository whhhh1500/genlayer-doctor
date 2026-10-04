import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
EXAMPLES = Path(__file__).parent.parent / "examples" / "contracts"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def fixture():
    return load


@pytest.fixture
def examples():
    return EXAMPLES


class FakeTransport:
    """Replays recorded Studio JSON-RPC responses keyed by method (+ optional matcher)."""

    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def __call__(self, url, payload, timeout):
        self.calls.append(payload)
        r = self.responses[payload["method"]]
        return r(payload) if callable(r) else r


@pytest.fixture
def fake_transport():
    return FakeTransport
