@app.post("/issues")
def add_issue():
   
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

@app.get("/issues/all")
def get_all_issues():
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



@app.get("/issues/by-store")
def get_issues_by_store():
    
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

@app.get("/issues/search")
def search_issues():

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

@app.post("/issues/delete")
def delete_issue():
  
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

