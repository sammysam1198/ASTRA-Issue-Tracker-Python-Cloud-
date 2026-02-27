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
    conn.close()

    return jsonify(rows), 200

