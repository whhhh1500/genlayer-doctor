"""Static checks for the GenVM runner header (the `# { "Depends": ... }` line).

GenVM decides which runtime executes a contract from the JSON comment on the first
line of the file. Getting it wrong does not show up as a failed transaction: the
deploy is FINALIZED with MAJORITY_AGREE, but every node's execution result is
`ERROR / invalid_contract`, and the contract address is unusable.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .findings import Finding

# Runner hash used by the current GenLayer docs and boilerplate (docs.genlayer.com, 2026-10).
RECOMMENDED_RUNNERS = {
    "py-genlayer": "1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6",
}
KNOWN_RUNNER_NAMES = {"py-genlayer", "py-genlayer-multi", "py-lib-genlayer-embeddings", "py-lib-genlayer-std"}
FLOATING_REFS = {"test", "latest"}
# Nix-style base32 alphabet used by GenVM runner hashes (no e, o, u, t).
NIX32 = re.compile(r"^[0123456789abcdfghijklmnpqrsvwxyz]{52}$")
HEADER_LINE = re.compile(r"^\s*#\s*(\{.*\})\s*$")


@dataclass
class Dependency:
    runner: str
    ref: str
    raw: str


@dataclass
class HeaderInfo:
    line: int | None = None
    raw: str | None = None
    data: object = None
    dependencies: list[Dependency] = field(default_factory=list)


def _collect_depends(node: object, out: list[str]) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "Depends" and isinstance(v, str):
                out.append(v)
            else:
                _collect_depends(v, out)
    elif isinstance(node, list):
        for item in node:
            _collect_depends(item, out)


def parse_header(source: str) -> tuple[HeaderInfo, list[Finding]]:
    info = HeaderInfo()
    findings: list[Finding] = []
    lines = source.splitlines()

    first_idx = next((i for i, l in enumerate(lines) if l.strip()), None)
    header_idx = None
    for i, l in enumerate(lines[:20]):
        if HEADER_LINE.match(l) and ("Depends" in l or "Seq" in l):
            header_idx = i
            break

    fix_hint = "Run `gldoctor fix <file> --write` to insert the recommended header."
    if header_idx is None:
        findings.append(Finding(
            "GLD001", "error",
            "Missing GenVM runner header. Line 1 must be a JSON comment such as "
            f'# {{ "Depends": "py-genlayer:{RECOMMENDED_RUNNERS["py-genlayer"]}" }}',
            line=1, hint=fix_hint))
        return info, findings

    info.line = header_idx + 1
    info.raw = lines[header_idx]
    if header_idx != 0 or first_idx != header_idx:
        findings.append(Finding(
            "GLD007", "warning",
            f"Runner header found on line {header_idx + 1}; GenVM expects it on line 1 (no shebang, blank line or docstring before it).",
            line=header_idx + 1, hint="Move the header to the very first line."))

    m = HEADER_LINE.match(lines[header_idx])
    try:
        info.data = json.loads(m.group(1))
    except json.JSONDecodeError as e:
        findings.append(Finding(
            "GLD002", "error", f"Runner header is not valid JSON: {e.msg} (column {e.colno}).",
            line=info.line, hint='Use double quotes, e.g. # { "Depends": "py-genlayer:<hash>" }'))
        return info, findings

    deps: list[str] = []
    _collect_depends(info.data, deps)
    if not deps:
        findings.append(Finding("GLD003", "error", 'Runner header has no "Depends" entry.', line=info.line, hint=fix_hint))
        return info, findings

    for raw in deps:
        if ":" not in raw:
            findings.append(Finding("GLD005", "error", f'Dependency "{raw}" is not in "<runner>:<hash>" form.', line=info.line, hint=fix_hint))
            continue
        runner, ref = raw.split(":", 1)
        info.dependencies.append(Dependency(runner, ref, raw))
        if runner not in KNOWN_RUNNER_NAMES:
            findings.append(Finding("GLD008", "warning", f'Unknown runner "{runner}" (typo?). Known: {", ".join(sorted(KNOWN_RUNNER_NAMES))}.', line=info.line))
        if ref in FLOATING_REFS:
            findings.append(Finding(
                "GLD004", "error",
                f'Runner "{raw}" uses the floating ref ":{ref}". GenVM rejects :test/:latest outside debug mode '
                "(Studio, testnets): the deploy is ACCEPTED/FINALIZED but execution fails with `invalid_contract`.",
                line=info.line,
                hint=f"Pin a runner hash, e.g. py-genlayer:{RECOMMENDED_RUNNERS['py-genlayer']} (`gldoctor fix --write`)."))
            continue
        if not NIX32.match(ref):
            findings.append(Finding(
                "GLD005", "error", f'Runner ref "{ref}" is not a 52-character GenVM hash.', line=info.line, hint=fix_hint))
            continue
        rec = RECOMMENDED_RUNNERS.get(runner)
        if rec and ref != rec:
            findings.append(Finding(
                "GLD006", "warning",
                f'"{runner}" is pinned to {ref[:10]}…, the current docs use {rec[:10]}…. Older runners may lack APIs or be '
                "unsupported on the target network.",
                line=info.line, hint="Confirm with `gldoctor check --network <net>` (dry run) or update with `gldoctor fix --write`."))
    return info, findings


def recommended_header(runner_hash: str | None = None) -> str:
    h = runner_hash or RECOMMENDED_RUNNERS["py-genlayer"]
    return f'# {{ "Depends": "py-genlayer:{h}" }}'


def fix_source(source: str, runner_hash: str | None = None) -> str:
    """Return source with a pinned py-genlayer runner header on line 1.

    * existing header: every `py-genlayer:<ref>` inside it is re-pinned, other
      dependencies (e.g. in a "Seq" list) are preserved, and the header is moved to line 1;
    * no header: the recommended header is inserted.
    """
    h = runner_hash or RECOMMENDED_RUNNERS["py-genlayer"]
    lines = source.splitlines(keepends=True)
    header = None
    for i, l in enumerate(lines[:20]):
        if HEADER_LINE.match(l.rstrip("\r\n")) and ("Depends" in l or "Seq" in l):
            header = lines.pop(i).rstrip("\r\n")
            break
    valid_json = False
    if header is not None:
        try:
            json.loads(HEADER_LINE.match(header).group(1))
            valid_json = True
        except (json.JSONDecodeError, AttributeError):
            valid_json = False
    if header is None or not valid_json or "py-genlayer:" not in header:
        header = recommended_header(h)
    else:
        header = re.sub(r"py-genlayer:[^\"'\s}]*", f"py-genlayer:{h}", header)
    while lines and not lines[0].strip():
        lines.pop(0)
    return header + "\n" + "".join(lines)
