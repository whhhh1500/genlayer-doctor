"""`gldoctor check`: static header checks + optional gasless dry run on a GenLayer node."""

from __future__ import annotations

import ast
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .diagnose import findings_from_genvm_error, parse_genvm_error
from .findings import Finding
from .header import parse_header
from .rpc import RpcClient, RpcError


@dataclass
class CheckResult:
    path: str
    findings: list[Finding] = field(default_factory=list)
    schema: dict | None = None

    def to_dict(self) -> dict:
        return {"path": self.path, "findings": [f.to_dict() for f in self.findings], "schema": self.schema}


def summarize_schema(schema: dict) -> list[str]:
    out = []
    ctor = schema.get("ctor") or {}
    params = ", ".join(f"{n}: {t}" for n, t in ctor.get("params", []))
    out.append(f"constructor({params})")
    for name, m in sorted((schema.get("methods") or {}).items()):
        p = ", ".join(f"{n}: {t}" for n, t in m.get("params", []))
        kind = "view" if m.get("readonly") else "write"
        if m.get("payable"):
            kind += ", payable"
        out.append(f"{name}({p}) -> {m.get('ret', 'null')}  [{kind}]")
    return out


def run_genvm_lint(path: str) -> list[Finding]:
    exe = shutil.which("genvm-lint")
    if not exe:
        return [Finding("GLD301", "warning", "--with-genvm-lint given but `genvm-lint` is not installed (pip install genvm-linter).")]
    proc = subprocess.run([exe, "lint", path], capture_output=True, text=True)
    text = (proc.stdout + proc.stderr).strip()
    sev = "error" if proc.returncode else "info"
    return [Finding("GLD300", sev, f"genvm-lint lint exited {proc.returncode}", details=text.splitlines()[-15:])]


def check_file(path: str, client: RpcClient | None = None, with_genvm_lint: bool = False) -> CheckResult:
    res = CheckResult(path=path)
    try:
        source = Path(path).read_text(encoding="utf-8")
    except OSError as e:
        res.findings.append(Finding("GLD000", "error", f"cannot read file: {e}"))
        return res

    _, hdr = parse_header(source)
    res.findings.extend(hdr)

    try:
        ast.parse(source, filename=path)
    except SyntaxError as e:
        res.findings.append(Finding("GLD010", "error", f"Python syntax error: {e.msg}", line=e.lineno,
                                    details=[(e.text or "").rstrip()] if e.text else []))

    if with_genvm_lint:
        res.findings.extend(run_genvm_lint(path))

    if client is None:
        return res

    try:
        res.schema = client.schema_for_code(source)
    except RpcError as e:
        if e.code == -32601 or ("not found" in e.message.lower() and "method" in e.message.lower()):
            res.findings.append(Finding("GLD202", "warning",
                f"{client.url} does not support gen_getContractSchemaForCode; dry run skipped (use studionet or localnet)."))
        elif e.code is None:
            res.findings.append(Finding("GLD203", "warning", f"dry run skipped: {e.message}"))
        else:
            res.findings.extend(findings_from_genvm_error(parse_genvm_error(e.message), "Dry run on node failed"))
        return res

    res.findings.append(Finding("GLD200", "info", "Dry run OK: the node loaded the contract and produced its ABI.",
                                details=summarize_schema(res.schema or {})))
    return res
