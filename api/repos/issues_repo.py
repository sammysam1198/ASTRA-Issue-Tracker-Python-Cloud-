import json
from flask import Flask, jsonify, request


@app.post("/issues")
def add_issue():
    """
    Add a new issue to the database.

    Expected JSON body:
    {
      "store_name": "Store 123 - Main St",
      "issue": {
        "Name": "...",              # or "Issue Name"
        "Priority": "...",
        "Store Number": "12345",
        "Computer Number": "PC-01",
        "Device": "Computer",       # <--- device type
        "Category": "Hardware",     # <--- problem category
        "Description": "...",
        "Narrative": "",
        "Replicable?": "Yes/No",
        "Global Issue": "False",
        "Global Number": "12",
        "Status": "Unresolved",
        "Resolution": ""
      }
    }
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    store_name = data.get("store_name")
    issue = data.get("issue")

    if not store_name or not issue:
        return jsonify({"error": "store_name and issue are required"}), 400

    # Pull fields out of the issue dict
    store_number = issue.get("Store Number")
    issue_name = issue.get("Name") or issue.get("Issue Name")
    priority = issue.get("Priority")
    computer_number = issue.get("Computer Number")
    device_type = issue.get("Device")          # <--- NEW
    category = issue.get("Category")           # <--- NEW
    description = issue.get("Description")
    narrative = issue.get("Narrative", "")
    replicable = issue.get("Replicable?")
    raw_global_issue = issue.get("Global Issue")
    raw_global_num = issue.get("Global Number")
    status = issue.get("Status")
    resolution = issue.get("Resolution", "")

    # --- NORMALIZE global_issue TO BOOL ---
    if isinstance(raw_global_issue, bool):
        global_issue = raw_global_issue
    else:
        global_issue = str(raw_global_issue).strip().lower() in ("true", "yes", "y", "1")

    # --- NORMALIZE global_num TO INT OR NONE ---
        # --- NORMALIZE global_num TO INT OR NONE ---
    if raw_global_num not in (None, ""):
        try:
            global_num = int(raw_global_num)
        except ValueError:
            return jsonify({"error": "Global Number must be an integer"}), 400
    else:
        global_num = None

    
    conn = get_db_conn()
    cur = conn.cursor()
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
            global_num if global_num is not None else None,
            status,
            resolution,
        ),
    )
    new_issue = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"message": "Issue added", "issue": new_issue}), 201




@app.get("/issues/all")
def get_all_issues():
    """
    Return all issues in the DB, ordered by store_number then id.

    Response: JSON list of issue rows (same shape as /issues/by-store)
    """
    try:
        conn = get_db_conn()
    except Exception as e:
        return jsonify({"error": f"Database connection error: {e}"}), 500

    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT *
            FROM issues
            ORDER BY store_number, id;
            """
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        return jsonify({"error": f"Database query error: {e}"}), 500

    # /issues/by-store returns a plain list, so we match that:
    return jsonify(rows), 200


@app.get("/issues/by-store")
def get_issues_by_store():
    """
    Get issues for a specific store.

    Query params:
      ?store_number=123   OR   ?store_name=Store%20123...

    Returns a list of issues from the DB.
    """
    store_number = request.args.get("store_number")
    store_name = request.args.get("store_name")

    if not store_number and not store_name:
        return jsonify({"error": "store_number or store_name is required"}), 400

    conn = get_db_conn()
    cur = conn.cursor()

    if store_number:
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

    rows = cur.fetchall()
    cur.close()


    @app.post("/issues/update")
def update_issue():
    """
    Update an existing issue in the DB.

    Expected JSON body:
    {
      "issue_id": 123,
      "updated_issue": {
          "Store Name": "...",
          "Store Number": "12345",
          "Name": "...", or "Issue Name": "...",
          "Priority": "...",
          "Computer Number": "...",
          "Device": "Computer",
          "Category": "Hardware",
          "Description": "...",
          "Narrative": "...",
          "Replicable?": "...",
          "Global Issue": "FALSE",
          "Global Number": "12",
          "Status": "...",
          "Resolution": "..."
      }
    }
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    issue_id = data.get("issue_id")
    updated_issue = data.get("updated_issue")

    if issue_id is None or updated_issue is None:
        return jsonify({"error": "issue_id and updated_issue are required"}), 400

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

    # --- NORMALIZE global_issue ---
    if raw_global_issue is None:
        global_issue = None  # means "don't change it"
        
    elif isinstance(raw_global_issue, bool):
        global_issue = raw_global_issue
    else:
        global_issue = str(raw_global_issue).strip().lower() in ("true", "yes", "y", "1")

    # --- NORMALIZE global_num ---
    if raw_global_num not in (None, ""):
        try:
            global_num = int(raw_global_num)
        except ValueError:
            return jsonify({"error": "Global Number must be an integer"}), 400
    else:
        global_num = None

    conn = get_db_conn()
    cur = conn.cursor()
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
            category,
            description,
            narrative,
            replicable,
            global_issue,
            global_num if global_num is not None else None,
            status,
            resolution,
            issue_id,
        ),
    )
    updated_row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    if not updated_row:
        return jsonify({"error": "Issue not found"}), 404

    return jsonify({"message": "Issue updated", "issue": updated_row}), 200

@app.get("/issues/search")
def search_issues():
    """
    Advanced search for issues.

    Query params (all optional, at least one required):
      store_number=12345
      category=some_text
      status=Unresolved
      device=Computer
      name=Printer%20Down
      global_issue=True

    All text fields use ILIKE '%value%' (case-insensitive, partial match).
    """
    store_number = request.args.get("store_number")
    category = request.args.get("category")   # maps to device_type
    status = request.args.get("status")
    device = request.args.get("device")       # also maps to device_type
    name = request.args.get("name")           # maps to issue_name
    global_issue = request.args.get("global_issue")

    if not any([store_number, category, status, device, name, global_issue]):
        return jsonify({"error": "At least one search parameter is required"}), 400

    conn = get_db_conn()
    cur = conn.cursor()

    query = "SELECT * FROM issues WHERE 1=1"
    params = []

    if store_number:
        query += " AND store_number = %s"
        params.append(int(store_number))

    # In your current schema, 'category' and 'device' both map to device_type.
    if category:
        query += " AND category ILIKE %s"
        params.append(f"%{category}%")
    
    if status:
        query += " AND status ILIKE %s"
        params.append(f"%{status}%")

    if device:
        query += " AND device_type ILIKE %s"
        params.append(f"%{device}%")

    if name:
        query += " AND issue_name ILIKE %s"
        params.append(f"%{name}%")

    if global_issue is not None:
        val = str(global_issue).strip().lower()
        if val in ("true", "1", "yes", "y"):
            query += " AND global_issue = %s"
            params.append(True)
        elif val in ("false", "0", "no", "n"):
            query += " AND global_issue = %s"
            params.append(False)

    cur.execute(query, params)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify(rows), 200


@app.post("/issues/delete")
def delete_issue():
    """
    Delete an existing issue from the DB.

    Expected JSON body:
    {
      "issue_id": 123
    }
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    issue_id = data.get("issue_id")
    if issue_id is None:
        return jsonify({"error": "issue_id is required"}), 400

    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM issues WHERE id = %s RETURNING *;",
        (issue_id,),
    )
    deleted = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    if not deleted:
        return jsonify({"error": "Issue not found"}), 404

    return jsonify({"message": "Issue deleted", "issue": deleted}), 200

    conn.close()

    return jsonify(rows), 200

