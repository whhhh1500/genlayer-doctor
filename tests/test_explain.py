import base64

from genlayer_doctor.explain import decode_result, explain_transaction


def test_silent_failed_deploy_is_flagged(fixture):
    rep = explain_transaction(fixture("tx_deploy_bad_header.json")["result"])
    assert rep.status == "FINALIZED" and rep.result_name == "MAJORITY_AGREE"
    assert rep.verdict == "FAILED"
    assert rep.leader_execution == "ERROR"
    assert (rep.result_kind, rep.result_payload) == ("vm_error", "invalid_contract")
    codes = [f.code for f in rep.findings]
    assert codes == ["GLD101", "GLD004"]  # consensus-vs-execution + root cause in deployed source
    assert rep.type == "deploy" and rep.contract_address.startswith("0x")


def test_successful_deploy_and_write(fixture):
    dep = explain_transaction(fixture("tx_deploy_ok.json")["result"])
    assert dep.verdict == "OK" and dep.findings == [] and dep.result_kind == "return"
    wr = explain_transaction(fixture("tx_write_ok.json")["result"])
    assert wr.verdict == "OK" and wr.type == "call"
    assert sum(wr.votes.values()) == 5


def test_pending_and_canceled():
    assert explain_transaction({"hash": "0x1", "status": "PENDING"}).verdict == "PENDING"
    assert explain_transaction({"hash": "0x1", "status": "CANCELED"}).verdict == "FAILED"


def test_decode_result_variants():
    assert decode_result(base64.b64encode(b"\x00\x00").decode()) == ("return", "null")
    assert decode_result(base64.b64encode(b"\x01not enough balance").decode()) == ("user_error (rollback)", "not enough balance")
    assert decode_result({"status": "contract_error", "payload": "invalid_contract"}) == ("contract_error", "invalid_contract")
    assert decode_result("") == ("", "")


def test_genlayer_js_decoded_receipt_shape():
    # genlayer-js returns status_name + decoded dict results
    tx = {"hash": "0x2", "type": 1, "status": 5, "status_name": "ACCEPTED",
          "data": {"contract_address": "0xabc"},
          "consensus_data": {"leader_receipt": [{"execution_result": "ERROR",
                                                 "result": {"status": "contract_error", "payload": "invalid_contract"}}]}}
    rep = explain_transaction(tx)
    assert rep.verdict == "FAILED" and rep.contract_address == "0xabc"
