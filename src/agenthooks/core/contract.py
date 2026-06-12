from __future__ import annotations
import re
from dataclasses import dataclass

@dataclass(frozen=True)
class ContractVersion:
    major: int
    minor: int

    def __init__(self, version_str: str) -> None:
        m = re.fullmatch(r"(\d+)\.(\d+)", version_str.strip())
        if not m:
            raise ValueError(f"invalid contract version '{version_str}' — expected MAJOR.MINOR e.g. '1.0'")
        object.__setattr__(self, "major", int(m.group(1)))
        object.__setattr__(self, "minor", int(m.group(2)))

    def __le__(self, other: "ContractVersion") -> bool:
        return (self.major, self.minor) <= (other.major, other.minor)
    def __lt__(self, other: "ContractVersion") -> bool:
        return (self.major, self.minor) < (other.major, other.minor)
    def __ge__(self, other: "ContractVersion") -> bool:
        return (self.major, self.minor) >= (other.major, other.minor)
    def __gt__(self, other: "ContractVersion") -> bool:
        return (self.major, self.minor) > (other.major, other.minor)
    def __str__(self) -> str:
        return f"{self.major}.{self.minor}"


def check_compatibility(required: str | None, got: str | None) -> bool:
    if required is None:
        return True
    if got is None:
        return False
    got_v = ContractVersion(got)
    clauses = [c.strip() for c in required.split(",")]
    for clause in clauses:
        m = re.fullmatch(r"(>=|<=|>|<|==)?(\d+\.\d+)", clause)
        if not m:
            raise ValueError(f"invalid version clause '{clause}'")
        op, ver = m.group(1) or "==", m.group(2)
        req_v = ContractVersion(ver)
        ok = {">=": got_v >= req_v, "<=": got_v <= req_v, ">": got_v > req_v, "<": got_v < req_v, "==": got_v == req_v}[op]
        if not ok:
            return False
    return True
