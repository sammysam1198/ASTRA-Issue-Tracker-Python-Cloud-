@app.get("/devices/by-store")
def get_devices_by_store():

    conn = get_db_conn()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            device_uid,
            store_number,
            device_type,
            device_number,
            manufacturer,
            model,
            device_notes
        FROM store_devices
        WHERE store_number = %s
        ORDER BY device_type, device_number NULLS LAST, manufacturer, model;
        """,
        (store_number_int,),
    )

    rows = cur.fetchall()
    cur.close()
    conn.close()


def api_device_dryrun_action(store_number, device_type, device_number, manufacturer, model):
    """
    Returns: (ok:bool, action:str, reason_or_err:str|None)
    action in {"insert", "update", "skip", "error"}
    """
    conn = None
    try:
        conn = get_db_conn()
        cur = conn.cursor()

        dt = (device_type or "").strip()
        dn = (device_number or "").strip() or None
        mf = (manufacturer or "").strip() or None
        md = (model or "").strip() or None

        dt_norm = dt.strip().title()
        if dt_norm == "Cradlepoint":
            dt_norm = "CradlePoint"

        # Printer / CradlePoint: key = (store_number, device_type)
        if dt_norm in ("Printer", "CradlePoint"):
            cur.execute("""
                SELECT manufacturer, model
                FROM store_devices
                WHERE store_number=%s AND device_type=%s
                LIMIT 1
            """, (store_number, dt_norm))
            existing = cur.fetchone()
            return True, ("insert" if existing is None else "skip"), None

        # Phone: key = (store_number, device_number) where type=Phone
        if dt_norm == "Phone":
            if not dn:
                return False, "error", "Phone row missing device_number"
            cur.execute("""
                SELECT 1
                FROM store_devices
                WHERE store_number=%s AND device_type='Phone' AND device_number=%s
                LIMIT 1
            """, (store_number, dn))
            existing = cur.fetchone()
            return True, ("insert" if existing is None else "skip"), None

        # Computer: key = (store_number, device_number) where type=Computer
        if dt_norm == "Computer":
            if not dn:
                return False, "error", "Computer row missing device_number"
            cur.execute("""
                SELECT manufacturer, model
                FROM store_devices
                WHERE store_number=%s AND device_type='Computer' AND device_number=%s
                LIMIT 1
            """, (store_number, dn))
            existing = cur.fetchone()
            if existing is None:
                return True, "insert", None

            ex_mf, ex_md = existing
            # match your update rule: update if manufacturer OR model differs
            if (ex_mf != mf) or (ex_md != md):
                return True, "update", None
            return True, "skip", None

        return False, "error", f"Unsupported device type: {device_type}"

    except Exception as e:
        return False, "error", str(e)
    finally:
        if conn:
            conn.close()


def api_upsert_device(store_number, device_type, device_number, manufacturer, model):
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        dt = (device_type or "").strip().title()  # Normalize (e.g., "printer" -> "Printer")
        if dt == "Cradlepoint":
            dt = "CradlePoint"
        dn = (device_number or "").strip() or None
        mf = (manufacturer or "").strip() or None
        md = (model or "").strip() or None

        exists = False
        needs_update = False

        if dt in ("Printer", "CradlePoint"):
            # Key: store_number + device_type (no device_number)
            cur.execute("""
                SELECT manufacturer, model
                FROM store_devices
                WHERE store_number = %s AND device_type = %s
                LIMIT 1
            """, (store_number, dt))
            existing = cur.fetchone()
            if existing:
                exists = True
                # For these types, original logic: no update (DO NOTHING), so skip

        elif dt == "Phone":
            if not dn:
                return False, None, "Phone row missing device_number"
            # Key: store_number + device_number (with device_type fixed)
            cur.execute("""
                SELECT manufacturer, model
                FROM store_devices
                WHERE store_number = %s AND device_type = 'Phone' AND device_number = %s
                LIMIT 1
            """, (store_number, dn))
            existing = cur.fetchone()
            if existing:
                exists = True
                # For Phone, original logic: no update (DO NOTHING), so skip

        elif dt == "Computer":
            if not dn:
                return False, None, "Computer row missing device_number"
            # Key: store_number + device_number (with device_type fixed)
            cur.execute("""
                SELECT manufacturer, model
                FROM store_devices
                WHERE store_number = %s AND device_type = 'Computer' AND device_number = %s
                LIMIT 1
            """, (store_number, dn))
            existing = cur.fetchone()
            if existing:
                exists = True
                ex_mf, ex_md = existing
                # For Computer, original logic: update only if manufacturer or model differs
                if (ex_mf != mf) or (ex_md != md):
                    needs_update = True

        else:
            return False, None, f"Unsupported device type: {device_type}"

        if exists:
            if needs_update:
                # Update (only for Computer)
                cur.execute("""
                    UPDATE store_devices
                    SET manufacturer = %s,
                        model = %s,
                        updated_at = NOW()
                    WHERE store_number = %s
                      AND device_type = %s
                      AND device_number = %s
                """, (mf, md, store_number, dt, dn))
                conn.commit()
                return True, "update", None
            else:
                # Skip (no change needed)
                return True, "skip", None
        else:
            # Insert new row
            device_uid = str(uuid.uuid4())
            cur.execute("""
                INSERT INTO store_devices
                    (device_uid, store_number, device_type, device_number, manufacturer, model)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (device_uid, store_number, dt, dn, mf, md))
            conn.commit()
            return True, "insert", None

    except Exception as e:
        conn.rollback()
        err = str(e)
        if hasattr(e, "pgerror") and e.pgerror:
            err = e.pgerror
        return False, None, err

    finally:
        cur.close()
        conn.close()

def store_exists(cur, store_number: int) -> bool:
    cur.execute("SELECT 1 FROM stores WHERE store_number=%s LIMIT 1;", (store_number,))
    return cur.fetchone() is not None


@app.route("/admin/import_devices", methods=["POST"])
def import_devices():
    try:
        conn_check = get_db_conn()
        cur_check = conn_check.cursor()
        try:
            for idx, r in enumerate(rows):
                store_number = r.get("store_number") or r.get("Store Number")
                device_type  = r.get("device_type")  or r.get("Device Type")
                device_number= r.get("device_number")or r.get("Device Number")
                manufacturer = r.get("manufacturer") or r.get("Manufacturer")
                model        = r.get("model")        or r.get("Model")

                try:
                    store_number = int(str(store_number).strip())
                except Exception:
                    summary["error"] += 1
                    err_rows.append({"row_index": idx, "error": f"Bad Store Number: {store_number}", "row": r})
                    continue

               
                if not store_exists(cur_check, store_number):
                    summary["error"] += 1
                    err_rows.append({
                        "row_index": idx,
                        "error": f"Store {store_number} does not exist in stores table (FK would fail).",
                        "row": r
                    })
                    continue

                if dry_run:
                    ok, action, err = api_device_dryrun_action(
                        store_number, device_type, device_number, manufacturer, model
                    )
                    if ok:
                        summary[action if action in summary else "skip"] += 1
                    else:
                        summary["error"] += 1
                        err_rows.append({"row_index": idx, "error": err, "row": r})
                else:
                    ok, _, err = api_upsert_device(
                        store_number, device_type, device_number, manufacturer, model
                    )
                    if ok:
                        summary["applied"] += 1
                    else:
                        summary["error"] += 1
                        err_rows.append({"row_index": idx, "error": err, "row": r})
        finally:
            try:
                cur_check.close()
            except Exception:
                pass
            conn_check.close()
