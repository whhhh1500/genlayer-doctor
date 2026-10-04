from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

SEVERITY_ORDER = {"info": 0, "warning": 1, "error": 2}


@dataclass
class Finding:
    code: str
    severity: str  # "error" | "warning" | "info"
    message: str
    line: Optional[int] = None
    hint: Optional[str] = None
    details: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        return {k: v for k, v in d.items() if v not in (None, [], "")}


def worst(findings: list[Finding]) -> str:
    if not findings:
        return "info"
    return max((f.severity for f in findings), key=lambda s: SEVERITY_ORDER[s])


def has_errors(findings: list[Finding]) -> bool:
    return any(f.severity == "error" for f in findings)
