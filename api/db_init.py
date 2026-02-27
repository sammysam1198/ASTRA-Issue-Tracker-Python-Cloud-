# db_indef init_db():
    """Create/upgrade tables (issues, users, stores) and ensure new columns exist."""
    conn = get_db_conn()
    cur = conn.cursor()

    # =========================
    # ISSUES TABLE
    # =========================
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS issues (
            id SERIAL PRIMARY KEY,
            store_name TEXT NOT NULL,
            store_number INTEGER,
            issue_name TEXT,
            priority TEXT,
            computer_number TEXT,
            device_type TEXT,
            category TEXT,
            description TEXT,
            narrative TEXT,
            replicable TEXT,
            status TEXT,
            resolution TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            global_issue BOOLEAN NOT NULL DEFAULT FALSE,
            global_num INTEGER
        );
        """
    )

    
    # =========================
    # USERS TABLE
    # =========================
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            username TEXT NOT NULL,
            password_hash TEXT,
            pin_hash TEXT,
            has_password BOOLEAN NOT NULL DEFAULT FALSE,
            has_pin BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            last_login_at TIMESTAMPTZ
        );
        """
    )

    # =======================
    # Tech Table
    # =======================
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS store_devices (
            id SERIAL PRIMARY KEY,
            device_uid TEXT UNIQUE NOT NULL,
            store_number INTEGER NOT NULL REFERENCES stores(store_number),
            device_type TEXT NOT NULL,
            device_number TEXT,
            manufacturer TEXT,
            model TEXT,
            device_notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_store_devices_store_number
            ON store_devices(store_number);
        """
    )
    # ====================================================
    # Rules for importing new rows into the tech info table
    # ====================================================
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_store_devices_phone
        ON store_devices (store_number, device_number)
        WHERE device_type = 'Phone';
    """)

    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_store_devices_computer
        ON store_devices (store_number, device_number)
        WHERE device_type = 'Computer';
    """)

    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_store_devices_printer_cradlepoint
        ON store_devices (store_number, device_type)
        WHERE device_type IN ('Printer', 'CradlePoint');
    """)
    
    
    # =========================
    # STORES TABLE
    # =========================
    # Base definition (in case table doesn't exist yet)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS stores (
            id SERIAL PRIMARY KEY,
            store_number INTEGER UNIQUE NOT NULL,
            store_name TEXT NOT NULL,
            type TEXT,
            state TEXT,
            num_comp INTEGER,
            address TEXT,
            city TEXT,
            zip TEXT,
            phone TEXT,
            kiosk TEXT
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS schedule_employees (
            id SERIAL PRIMARY KEY,
            employee_uid TEXT UNIQUE NOT NULL,
            store_number INTEGER NOT NULL,
            full_name TEXT NOT NULL,
            role_title TEXT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            archived_until TIMESTAMP NULL,
            archive_reason TEXT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS schedule_availability (
            id SERIAL PRIMARY KEY,
            store_number INTEGER NOT NULL,
            day_of_week INTEGER NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),

            status TEXT NOT NULL DEFAULT 'STANDARD',
            -- allowed: STANDARD, CUSTOM, OFF, BLOCK

            start_time TIME NULL,
            end_time TIME NULL,

            source TEXT NOT NULL DEFAULT 'manual',
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

            UNIQUE (store_number, day_of_week)

        );
        """
    )
    cur.execute(
       """ 
        CREATE TABLE IF NOT EXISTS schedule_standard_hours (
            day_of_week INTEGER PRIMARY KEY CHECK (day_of_week BETWEEN 0 AND 6),
            start_time TIME NOT NULL,
            end_time TIME NOT NULL
        );
        """
    )


    

    # ======================
    # One Time Updates
    # ======================

    cur.execute(
        """
        INSERT INTO schedule_standard_hours (day_of_week, start_time, end_time) VALUES
            (0, '12:00', '16:00'),
            (1, '11:00', '19:00'),
            (2, '11:00', '19:00'),
            (3, '11:00', '19:00'),
            (4, '11:00', '19:00'),
            (5, '11:00', '19:00'),
            (6, '11:00', '19:00')
            ON CONFLICT (day_of_week) DO NOTHING;
        """
    )
        
    



    conn.commit()
    cur.close()
    conn.close()
it.py
