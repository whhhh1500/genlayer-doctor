import json

import pytest

from genlayer_doctor import cli, rpc


def run(capsys, *argv):
    code = cli.main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


def test_check_offline(capsys, examples):
    code, out, _ = run(capsys, "check", str(examples / "hello_ok.py"), str(examples / "bad_floating_runner.py"))
    assert code == 1
    assert "PASS" in out and "FAIL" in out and "GLD004" in out


def test_check_ok_exit_zero_and_json(capsys, examples):
    code, out, _ = run(capsys, "check", "--json", str(examples / "hello_ok.py"))
    assert code == 0
    data = json.loads(out)
    assert data["ok"] is True and data["rpc"] is None


def test_check_with_dry_run(monkeypatch, capsys, examples, fixture, fake_transport):
    good, bad = fixture("schema_ok.json"), fixture("schema_bad_header.json")
    ok_src = (examples / "hello_ok.py").read_text().encode().hex()
    t = fake_transport({"gen_getContractSchemaForCode": lambda p: good if p["params"][0] == ok_src else bad})
    monkeypatch.setattr(rpc, "http_transport", t)
    monkeypatch.setattr(rpc.RpcClient.__init__, "__defaults__", (60.0, t))
    code, out, _ = run(capsys, "check", "-n", "studionet", "--json",
                       str(examples / "hello_ok.py"), str(examples / "bad_floating_runner.py"))
    data = json.loads(out)
    assert code == 1
    ok, bad_res = data["results"]
    assert ok["schema"]["methods"]["set_greeting"]["readonly"] is False
    assert [f["code"] for f in ok["findings"]] == ["GLD200"]
    assert [f["code"] for f in bad_res["findings"]] == ["GLD004", "GLD004"]


def test_unsupported_method_degrades_to_warning(monkeypatch, capsys, examples, fake_transport):
    t = fake_transport({"gen_getContractSchemaForCode": {"error": {"code": -32601, "message": "Method not found"}}})
    monkeypatch.setattr(rpc.RpcClient.__init__, "__defaults__", (60.0, t))
    code, out, _ = run(capsys, "check", "-n", "testnet-asimov", str(examples / "hello_ok.py"))
    assert code == 0 and "GLD202" in out
    code, _, _ = run(capsys, "check", "--strict", "-n", "testnet-asimov", str(examples / "hello_ok.py"))
    assert code == 1


def test_explain_from_file(capsys, tmp_path, fixture):
    p = tmp_path / "tx.json"
    p.write_text(json.dumps(fixture("tx_deploy_bad_header.json")))
    code, out, _ = run(capsys, "explain", "--from-file", str(p))
    assert code == 1 and out.startswith("FAILED") and "GLD101" in out


def test_explain_via_rpc(monkeypatch, capsys, fixture, fake_transport):
    t = fake_transport({"eth_getTransactionByHash": fixture("tx_deploy_ok.json")})
    monkeypatch.setattr(rpc.RpcClient.__init__, "__defaults__", (60.0, t))
    code, out, _ = run(capsys, "explain", "0x07e7", "--json")
    assert code == 0 and json.loads(out)["verdict"] == "OK"
    assert t.calls[0]["params"] == ["0x07e7"]


def test_explain_requires_target(capsys):
    assert run(capsys, "explain")[0] == 2


def test_fix_dry_run_and_write(capsys, tmp_path, examples):
    p = tmp_path / "c.py"
    p.write_text((examples / "bad_floating_runner.py").read_text())
    code, out, _ = run(capsys, "fix", str(p))
    assert code == 1 and "+# { \"Depends\": \"py-genlayer:1jb45" in out
    assert "py-genlayer:test" in p.read_text()  # dry run did not modify
    assert run(capsys, "fix", "--write", str(p))[0] == 0
    assert run(capsys, "check", str(p))[0] == 0
    assert "already pinned" in run(capsys, "fix", str(p))[1]


def test_unknown_network_is_usage_error(capsys, examples):
    with pytest.raises(SystemExit):
        cli.main(["check", "-n", "mainnet", str(examples / "hello_ok.py")])


def test_user_agent_is_explicit():
    assert rpc.USER_AGENT.startswith("genlayer-doctor/")
