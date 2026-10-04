"""Turn raw GenVM / Studio error payloads into readable findings."""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field

from .findings import Finding

# (regex, code, explanation). Order matters: first match wins for the headline.
KNOWN_ERRORS: list[tuple[str, str, str]] = [
    (r":test/ :latest runner used in non-debug mode",
     "GLD004",
     "The runner header uses py-genlayer:test or :latest, which GenVM only accepts in debug mode. Pin a runner hash."),
    (r"SyntaxError|IndentationError",
     "GLD210",
     "Python syntax error in the contract (see traceback)."),
    (r"ModuleNotFoundError|ImportError",
     "GLD211",
     "An import is not available inside the GenVM runner. Only the bundled stdlib subset and `genlayer` are available."),
    (r"NameError",
     "GLD212",
     "A name is undefined at module load time (missing `from genlayer import *`?)."),
    (r"TypeError|ValueError|AttributeError|KeyError|AssertionError",
     "GLD213",
     "The contract raised an exception while loading or building its schema (see traceback)."),
    (r"invalid_contract",
     "GLD201",
     "GenVM refused to load the contract before running any code: usually the runner header is missing, malformed, "
     "floating (:test/:latest) or points at a runner the node does not have."),
    (r"exit_code \d+",
     "GLD214",
     "The contract process exited with an error (see stderr)."),
]

BENIGN = [
    r"VALIDATOR_QUORUM_REACHED",
    r"Validator execution cancelled after quorum",
    r"runner comment does not start with version",
    r"no backtrace attached",
    r"no memories attached",
]


@dataclass
class GenVMError:
    summary: str = ""
    stderr: str = ""
    stdout: str = ""
    result_kind: str = ""
    result_message: str = ""
    log_warnings: list[str] = field(default_factory=list)
    genvm_version: str = ""
    raw: str = ""

    def text_blob(self) -> str:
        return "\n".join([self.summary, self.stderr, self.result_message, *self.log_warnings])


def _from_payload(payload: dict, err: GenVMError) -> None:
    err.stderr = payload.get("stderr") or ""
    err.stdout = payload.get("stdout") or ""
    for entry in payload.get("genvm_log") or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("version") and not err.genvm_version:
            err.genvm_version = str(entry["version"])
        if entry.get("level") in ("warn", "error"):
            msg = str(entry.get("message", ""))
            if not any(re.search(b, msg) for b in BENIGN):
                err.log_warnings.append(msg)
    result = payload.get("result")
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            result = {"message": result}
    if isinstance(result, dict):
        err.result_kind = str(result.get("kind", ""))
        err.result_message = str(result.get("message", ""))


def parse_genvm_error(message: str) -> GenVMError:
    """Parse the `message` of a gen_getContractSchemaForCode / gen_call JSON-RPC error.

    Studio formats it as the Python repr of ('execution failed', {stdout, stderr, genvm_log, result}).
    """
    err = GenVMError(raw=message)
    parsed = None
    try:
        parsed = ast.literal_eval(message)
    except (ValueError, SyntaxError, MemoryError, RecursionError):
        parsed = None
    if isinstance(parsed, tuple) and parsed:
        err.summary = str(parsed[0])
        if len(parsed) > 1 and isinstance(parsed[1], dict):
            _from_payload(parsed[1], err)
    elif isinstance(parsed, dict):
        _from_payload(parsed, err)
    else:
        # Fallback: regex scraping
        err.summary = message.split(",", 1)[0].strip("(' ")
        for m in re.finditer(r"'message': '([^']*)'[^}]*'level': '(warn|error)'", message):
            if not any(re.search(b, m.group(1)) for b in BENIGN):
                err.log_warnings.append(m.group(1))
        m = re.search(r'"kind": "([^"]+)", "message": "([^"]+)"', message.replace('\\"', '"'))
        if m:
            err.result_kind, err.result_message = m.group(1), m.group(2)
        m = re.search(r"'stderr': '((?:[^'\\]|\\.)*)'", message)
        if m:
            err.stderr = m.group(1).encode().decode("unicode_escape", errors="replace")
    return err


def traceback_tail(stderr: str, n: int = 6) -> list[str]:
    lines = [l for l in stderr.strip().splitlines() if l.strip()]
    if not lines:
        return []
    # Keep the location of the user contract and the final exception line.
    out: list[str] = []
    for i, l in enumerate(lines):
        if '"/contract.py"' in l:
            out = lines[i:]
    return (out or lines)[-n:]


def classify(blob: str) -> tuple[str, str] | None:
    for pattern, code, explanation in KNOWN_ERRORS:
        if re.search(pattern, blob):
            return code, explanation
    return None


def findings_from_genvm_error(err: GenVMError, context: str) -> list[Finding]:
    blob = err.text_blob()
    hit = classify(blob)
    code, explanation = hit if hit else ("GLD299", "Unrecognised GenVM error.")
    details: list[str] = []
    if err.result_kind or err.result_message:
        details.append(f"result: {err.result_kind} {err.result_message}".strip())
    for w in err.log_warnings:
        details.append(f"genvm: {w}")
    details.extend(f"stderr: {l}" for l in traceback_tail(err.stderr))
    if err.genvm_version:
        details.append(f"genvm version: {err.genvm_version}")
    return [Finding(code, "error", f"{context}: {explanation}", details=details)]
