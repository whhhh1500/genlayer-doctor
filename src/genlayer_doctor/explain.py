"""Explain a GenLayer transaction: did it *really* succeed, and if not, why."""

from __future__ import annotations

import base64
import binascii
from collections import Counter
from dataclasses import dataclass, field

from .diagnose import classify, traceback_tail
from .findings import Finding
from .header import parse_header

TX_TYPES = {0: "send", 1: "deploy", 2: "call", 3: "upgrade"}
# First byte of a GenVM result blob.
RESULT_CODES = {0: "return", 1: "user_error (rollback)", 2: "vm_error"}
TERMINAL_OK = {"ACCEPTED", "FINALIZED"}
TERMINAL_BAD = {"CANCELED", "UNDETERMINED", "LEADER_TIMEOUT", "VALIDATORS_TIMEOUT"}


@dataclass
class TxReport:
    hash: str
    type: str = "?"
    status: str = "?"
    result_name: str = ""
    sender: str = ""
    to: str = ""
    contract_address: str = ""
    leader_execution: str = ""
    result_kind: str = ""
    result_payload: str = ""
    stderr: list[str] = field(default_factory=list)
    votes: dict = field(default_factory=dict)
    verdict: str = "UNKNOWN"  # OK | FAILED | PENDING | UNKNOWN
    findings: list[Finding] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k != "findings"}
        d["findings"] = [f.to_dict() for f in self.findings]
        return d


def decode_result(raw) -> tuple[str, str]:
    """Return (kind, payload) from a leader receipt `result` (base64 blob or decoded dict)."""
    if isinstance(raw, dict):
        return str(raw.get("status", "")), str(raw.get("payload", ""))
    if not isinstance(raw, str) or not raw:
        return "", ""
    try:
        blob = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        return "", raw
    if not blob:
        return "", ""
    kind = RESULT_CODES.get(blob[0], f"code_{blob[0]}")
    body = blob[1:]
    if blob[0] == 0:
        payload = "null" if body == b"\x00" else f"<{len(body)} bytes calldata>"
    else:
        payload = body.decode("utf-8", errors="replace")
    return kind, payload


def _status_name(tx: dict) -> str:
    s = tx.get("status_name") or tx.get("statusName") or tx.get("status")
    return str(s).upper() if s is not None else "?"


def explain_transaction(tx: dict) -> TxReport:
    rep = TxReport(hash=str(tx.get("hash", "")))
    t = tx.get("type")
    rep.type = TX_TYPES.get(t, str(t)) if isinstance(t, int) else str(t or "?")
    rep.status = _status_name(tx)
    rep.result_name = str(tx.get("result_name") or "")
    rep.sender = str(tx.get("from_address") or tx.get("sender") or "")
    rep.to = str(tx.get("to_address") or tx.get("recipient") or "")
    data = tx.get("data") or {}
    rep.contract_address = str(data.get("contract_address") or (rep.to if rep.type == "deploy" else ""))

    cd = tx.get("consensus_data") or {}
    leaders = cd.get("leader_receipt") or []
    if isinstance(leaders, dict):
        leaders = [leaders]
    leader = leaders[0] if leaders else {}
    rep.leader_execution = str(leader.get("execution_result") or "")
    rep.result_kind, rep.result_payload = decode_result(leader.get("result"))
    gr = leader.get("genvm_result") or {}
    rep.stderr = traceback_tail(str(gr.get("stderr") or ""))

    lr = tx.get("last_round") or {}
    names = lr.get("validator_votes_name")
    if names:
        rep.votes = dict(Counter(names))
    else:
        rep.votes = dict(Counter(str(v.get("vote")) for v in cd.get("validators") or [] if isinstance(v, dict)))

    # ---- verdict -----------------------------------------------------------
    if rep.status in TERMINAL_BAD:
        rep.verdict = "FAILED"
        rep.findings.append(Finding("GLD102", "error", f"Transaction ended with status {rep.status}."))
    elif rep.status not in TERMINAL_OK:
        rep.verdict = "PENDING"
        rep.findings.append(Finding("GLD103", "info", f"Transaction is still {rep.status}; re-run later."))
    elif rep.leader_execution and rep.leader_execution != "SUCCESS":
        rep.verdict = "FAILED"
        blob = " ".join([rep.result_kind, rep.result_payload, *rep.stderr])
        hit = classify(blob)
        msg = (f"Status is {rep.status}"
               + (f" / {rep.result_name}" if rep.result_name else "")
               + f", but the leader's execution result is {rep.leader_execution} "
               + f"({rep.result_kind or 'error'}: {rep.result_payload or 'n/a'}). "
               + "Consensus only means validators agreed on the outcome — the outcome was an error.")
        details = [f"stderr: {l}" for l in rep.stderr]
        if rep.type == "deploy":
            details.append(f"contract at {rep.contract_address} is NOT usable; fix the code and redeploy.")
        rep.findings.append(Finding("GLD101", "error", msg, hint=hit[1] if hit else None, details=details))
    else:
        rep.verdict = "OK"

    # ---- inspect deployed source ----------------------------------------
    code_b64 = data.get("contract_code")
    if rep.type == "deploy" and isinstance(code_b64, str) and code_b64:
        try:
            src = base64.b64decode(code_b64).decode("utf-8", errors="replace")
        except (binascii.Error, ValueError):
            src = ""
        if src:
            _, hdr = parse_header(src)
            for f in hdr:
                f.message = "deployed code: " + f.message
            rep.findings.extend(hdr)
    return rep
