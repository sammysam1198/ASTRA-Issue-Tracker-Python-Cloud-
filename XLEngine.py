#XLEngine.py

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


# -------------------------
# Session state
# -------------------------

@dataclass
class XLSetupSession:
    workbook_filename: str = "AVL_DB_2D.xlsx"  # you can set this at startup
    active_version: str = field(init=False)
    revert_active: bool = False
    revert_version: Optional[str] = None

    def __post_init__(self):
        self.active_version = extract_version_from_filename(self.workbook_filename)

    def set_workbook(self, filename: str):
        self.workbook_filename = filename
        self.active_version = extract_version_from_filename(filename)

    def set_revert(self, version: Optional[str]):
        if version is None:
            self.revert_active = False
            self.revert_version = None
        else:
            self.revert_active = True
            self.revert_version = version


def extract_version_from_filename(filename: str) -> str:
    """
    Safe version parsing:
    - Prefer pattern like _2D or _10B at end of stem.
    """
    stem = re.sub(r"\.[^.]+$", "", filename)  # drop extension
    m = re.search(r"_(\d+)([A-Za-z])$", stem)
    if not m:
        # fallback: last two chars of stem (your original idea)
        return stem[-2:]
    return f"{m.group(1)}{m.group(2).upper()}"


# -------------------------
# Parser skeleton
# -------------------------

def parse_xlscript_block(script: str) -> List[Dict[str, Any]]:
    """
    Skeleton parser:
    Supports:
      - UPDATE BY EX=NN WITH: ... (captures raw lines for now)
      - RMV ...
      - RRMV ...
      - RVRT=2C / RVRT OFF
    Returns list of action dicts.
    """
    lines = [ln.rstrip() for ln in script.splitlines() if ln.strip() != ""]
    if not lines:
        return []

    first = lines[0].lstrip()

    # RVRT
    if first.upper().startswith("RVRT"):
        # RVRT=2C or RVRT 2C or RVRT OFF
        m = re.search(r"RVRT\s*=?\s*([0-9]+[A-Za-z]|OFF)", first, flags=re.IGNORECASE)
        if not m:
            return [{"type": "ERROR", "message": "RVRT syntax invalid. Use RVRT=2C or RVRT OFF.", "raw": first}]
        val = m.group(1).upper()
        return [{
            "type": "RVRT",
            "target": {"version": None if val == "OFF" else val},
            "payload": {},
        }]

    # RRMV
    if first.upper().startswith("RRMV"):
        m = re.search(r"ROW\s*=\s*(\d+)", first, flags=re.IGNORECASE)
        if not m:
            return [{"type": "ERROR", "message": "RRMV requires ROW=<number>.", "raw": first}]
        return [{
            "type": "RRMV",
            "target": {"row": int(m.group(1))},
            "payload": {},
        }]

    # RMV (kept generic for now)
    if first.upper().startswith("RMV"):
        return [{
            "type": "RMV",
            "target": {"raw": first},
            "payload": {},
        }]

    # ADD ROW ...
    if first.upper().startswith("ADD "):
        # Expected:
        # ADD ROW AFT=49 AS:
        #   ROW="Michael Chavez"
        #   WITH:
        #       DAY=a
        #       AVL=...
        #       SNUM!=...
        m = re.search(
            r"ADD\s+ROW\s+(AFT|BFR)\s*=\s*(\d+)\s+AS\s*:\s*$",
            first,
            flags=re.IGNORECASE
        )
        if not m:
            return [{"type": "ERROR", "message": 'ADD syntax invalid. Use: ADD ROW AFT=49 AS:', "raw": first}]

        placement = m.group(1).upper()  # AFT or BFR
        anchor = int(m.group(2))

        statements = [ln.lstrip() for ln in lines[1:]]  # ignore leading tabs/spaces

        row_name = None
        with_lines: List[str] = []
        in_with = False

        for s in statements:
            if s.upper().startswith("WITH"):
                in_with = True
                continue

            if not in_with:
                mm = re.search(r'^ROW\s*=\s*"(.*)"\s*$', s, flags=re.IGNORECASE)
                if mm:
                    row_name = mm.group(1).strip()
            else:
                with_lines.append(s)

        return [{
            "type": "ADD",
            "target": {"where": placement, "anchor": anchor},
            "payload": {
                "row_name": row_name,
                "with_raw": with_lines
            }
        }]


    # UPDATE BY EX
    if first.upper().startswith("UPDATE BY EX"):
        m = re.search(r"EX\s*=\s*(\d+)", first, flags=re.IGNORECASE)
        if not m:
            return [{"type": "ERROR", "message": "UPDATE requires EX=<number>.", "raw": first}]
        ex = int(m.group(1))

        # For skeleton: store the remaining lines as "statements"
        statements = [ln.lstrip() for ln in lines[1:]]  # ignore leading tabs/spaces

        return [{
            "type": "UPDATE",
            "target": {"ex": ex},
            "payload": {
                "statements_raw": statements
            },
        }]

    # Unknown
    return [{"type": "ERROR", "message": "Unknown command.", "raw": first}]


# -------------------------
# Dry-run planner (human readable)
# -------------------------

def plan_actions(actions: List[Dict[str, Any]], session: XLSetupSession) -> List[str]:
    plan: List[str] = []
    ctx = f"(Active {session.active_version}" + (f", RVRT={session.revert_version})" if session.revert_active else ")")

    for a in actions:
        t = a.get("type")
        if t == "ERROR":
            plan.append(f"ERROR: {a.get('message')}  |  RAW: {a.get('raw')}")
            continue

        if t == "RVRT":
            v = a["target"]["version"]
            if v is None:
                plan.append(f"RVRT OFF {ctx} -> overlay disabled")
            else:
                plan.append(f"RVRT {v} {ctx} -> overlay enabled (single active reversion)")
            continue

        if t == "RRMV":
            plan.append(f"RRMV ROW={a['target']['row']} {ctx} -> destructive row delete; rows below shift up")
            continue

        if t == "RMV":
            plan.append(f"RMV {a['target']['raw']} {ctx} -> structural remove (non-retrograde placeholder)")
            continue

        if t == "ADD":
            where = a["target"]["where"]
            anchor = a["target"]["anchor"]
            name = a["payload"].get("row_name") or "(missing ROW=\"...\")"
            plan.append(f"ADD ROW {where}={anchor} {ctx}")
            plan.append(f'  - ROW="{name}"')
            with_raw = a["payload"].get("with_raw", [])
            if with_raw:
                plan.append("  - WITH:")
                for s in with_raw:
                    plan.append(f"    - {s}")
            continue


        if t == "UPDATE":
            ex = a["target"]["ex"]
            stmts = a["payload"].get("statements_raw", [])
            plan.append(f"UPDATE EX={ex} {ctx}")
            if not stmts:
                plan.append("  - (no statements)")
            else:
                for s in stmts:
                    plan.append(f"  - {s}")
            continue

        plan.append(f"(Unhandled action type: {t})")

    return plan


# -------------------------
# Buffered REPL engine
# -------------------------

SINGLE_LINE_PREFIXES = ("RRMV", "RMV", "RVRT")


def is_block_header(line: str) -> bool:
    """
    Returns True if the line starts a multi-line block that MUST be buffered
    (even if the buffer is currently empty).
    """
    up = line.strip().upper()
    return (
        up.startswith("UPDATE BY EX") and "WITH" in up  # UPDATE BY EX=.. WITH:
        or up.startswith("ADD ROW") and "AS" in up      # ADD ROW AFT=.. AS:
    )

class XLScriptBufferedRepl:
    def __init__(self, session: XLSetupSession):
        self.session = session
        self._buffer: List[str] = []

    def feed_line(self, line: str) -> Dict[str, Any]:
        """
        Implements your rules:
          - Leading whitespace ignored for commands.
          - Blank line executes buffered block.
          - Single-line commands execute immediately if buffer is empty.
        Returns a dict:
          {"executed": bool, "script": str|None, "actions": [...], "plan": [str]}
        """
        raw = line.rstrip("\n")
        stripped_right = raw.rstrip()

        # Blank line => execute buffer (if any)
        if stripped_right == "":
            if not self._buffer:
                return {"executed": False, "script": None, "actions": [], "plan": []}
            script = "\n".join(self._buffer).strip("\n")
            self._buffer.clear()
            actions = parse_xlscript_block(script)
            plan = plan_actions(actions, self.session)
            return {"executed": True, "script": script, "actions": actions, "plan": plan}

        # Non-blank: ignore leading whitespace
        normalized = stripped_right.lstrip()

        # If this is a block header, ALWAYS buffer it (never execute immediately)
        if is_block_header(normalized):
            self._buffer.append(normalized)
            return {"executed": False, "script": None, "actions": [], "plan": []}

        # Single-line immediate only when buffer empty (RMV/RRMV/RVRT)
        up = normalized.upper()
        if not self._buffer and up.startswith(SINGLE_LINE_PREFIXES):
            actions = parse_xlscript_block(normalized)
            plan = plan_actions(actions, self.session)
            return {"executed": True, "script": normalized, "actions": actions, "plan": plan}

        # Otherwise buffer it
        self._buffer.append(normalized)
        return {"executed": False, "script": None, "actions": [], "plan": []}
