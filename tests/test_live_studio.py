"""Opt-in live tests against the hosted Studio network: GLDOCTOR_LIVE=1 pytest -m live"""
import os

import pytest

from genlayer_doctor.check import check_file
from genlayer_doctor.rpc import RpcClient

pytestmark = [pytest.mark.live, pytest.mark.skipif(not os.environ.get("GLDOCTOR_LIVE"), reason="set GLDOCTOR_LIVE=1")]
RPC = "https://studio.genlayer.com/api"


def test_chain_id():
    assert RpcClient(RPC).chain_id() == 61999


@pytest.mark.parametrize("name,expected", [
    ("hello_ok.py", "GLD200"),
    ("bad_floating_runner.py", "GLD004"),
    ("missing_header.py", "GLD201"),
    ("syntax_error.py", "GLD210"),
    ("bad_import.py", "GLD211"),
])
def test_dry_run_codes(examples, name, expected):
    res = check_file(str(examples / name), client=RpcClient(RPC))
    assert expected in [f.code for f in res.findings]
