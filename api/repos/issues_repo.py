# api/repos/issues_repo.py

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from db import get_db_conn  # db.py at project root (same level as /api folder)


# -----------------------------
# Helpers (moved from api_server.py logic)
# -----------------------------

def _parse_bool(value: Any) -> bool:
    """
    Your API accepts bool OR strings like "true/false", "yes/no", "1/0".
    """
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "yes", "y", "1")


def _parse_int_or_none(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    return int(value)


# -----------------------------
# Repo functions (DB-only)
# -----------------------------

def insert_issue(store_name: str, issue: Dict[str, Any]) -> Dict[str, Any]:
    """
    Insert a new issue row into Postgres and return the inserted row.

    This is the DB-equivalent of your /issues POST endpoint.
    """
    if not store_name or not issue:
        raise ValueError("store_name and issue are required")

    store_number = issue.get("Store Number")
    issue_name = issue.get("Name") or issue.get("Issue Name")
    priority = issue.get("Priority")
    computer_number = issue.get("Computer Number")
    device_type = issue.get("Device")
    category = issue.get("Category")
    description = issue.get("Description")
    narrative = issue.get("Narrative", "")
    replicable = issue.get("Replicable?")
    raw_global_issue = issue.get("Global Issue")
    raw_global_num = issue.get("Global Number")
    status = issue.get("Status")
    resolution = issue.get("Resolution", "")

    global_issue = _parse_bool(raw_global_issue)
    try:
        global_num = _parse_int_or_none(raw_global_num)
    except ValueError:
        raise ValueError("Global Number must be an integer")

    conn = get_db_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO issues (
                store_name, store_number, issue_name, priority,
                computer_number, device_type, category,
                description, narrative, replicable, global_issue,
                global_num, status, resolution
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *;
            """,
            (
                store_name,
                int(store_number) if store_number is not None else None,
                issue_name,
                priority,
                computer_number,
                device_type,
                category,
                description,
                narrative,
                replicable,
                global_issue,
                global_num,
                status,
                resolution,
            ),
        )
        row = cur.fetchone()
        conn.commit()
        return row
    finally:
        cur.close()
        conn.close()


def fetch_all_issues() -> List[Dict[str, Any]]:
    """
    DB-equivalent of your /issues/all GET endpoint.
    """
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT *
            FROM issues
            ORDER BY store_number, id;
            """
        )
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()


def fetch_issues_by_store(
    *,
    store_number: Optional[int] = None,
    store_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    DB-equivalent of your /issues/by-store GET endpoint.
    """
    if store_number is None and not store_name:
        raise ValueError("store_number or store_name is required")

    conn = get_db_conn()
    cur = conn.cursor()
    try:
        if store_number is not None:
            cur.execute(
                """
                SELECT * FROM issues
                WHERE store_number = %s
                ORDER BY id;
                """,
                (int(store_number),),
            )
        else:
            cur.execute(
                """
                SELECT * FROM issues
                WHERE store_name = %s
                ORDER BY id;
                """,
                (store_name,),
            )
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()


def update_issue_row(issue_id: int, updated_issue: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    DB-equivalent of your /issues/update POST endpoint.
    Returns the updated row or None if not found.
    """
    if issue_id is None or updated_issue is None:
        raise ValueError("issue_id and updated_issue are required")

    store_name = updated_issue.get("Store Name") or updated_issue.get("Store_Name")
    store_number = updated_issue.get("Store Number")
    issue_name = updated_issue.get("Name") or updated_issue.get("Issue Name")
    priority = updated_issue.get("Priority")
    computer_number = updated_issue.get("Computer Number")
    device_type = updated_issue.get("Device")
    category = updated_issue.get("Category")
    description = updated_issue.get("Description")
    narrative = updated_issue.get("Narrative", "")
    replicable = updated_issue.get("Replicable?")
    raw_global_issue = updated_issue.get("Global Issue")
    raw_global_num = updated_issue.get("Global Number")
    status = updated_issue.get("Status")
    resolution = updated_issue.get("Resolution", "")

    # Match your existing endpoint behavior:
    # - global_issue: if None -> don't change it
    # - global_num: if ""/None -> becomes None (COALESCE keeps existing)
    if raw_global_issue is None:
        global_issue = None
    else:
        global_issue = _parse_bool(raw_global_issue)

    try:
        global_num = _parse_int_or_none(raw_global_num)
    except ValueError:
        raise ValueError("Global Number must be an integer")

    conn = get_db_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE issues
            SET
                store_name   = COALESCE(%s, store_name),
                store_number = COALESCE(%s, store_number),
                issue_name   = %s,
                priority     = %s,
                computer_number = %s,
                device_type  = %s,
                category     = %s,
                description  = %s,
                narrative    = %s,
                replicable   = %s,
                global_issue = COALESCE(%s, global_issue),
                global_num   = COALESCE(%s, global_num),
                status       = %s,
                resolution   = %s,
                updated_at   = NOW()
            WHERE id = %s
            RETURNING *;
            """,
            (
                store_name,
                int(store_number) if store_number is not None else None,
                issue_name,
                priority,
                computer_number,
                device_type,
                category
