"""Small forward-only upgrades for installations created before version 10."""
from sqlalchemy import inspect, text


def ensure_v10_schema(engine):
    additions = {
        "users": {"account_type": "VARCHAR(20) DEFAULT ''", "phone": "VARCHAR(40) DEFAULT ''", "staff_notes": "TEXT DEFAULT ''"},
        "halaqa_students": {
            "recipient_type": "VARCHAR(20) DEFAULT 'guardian'",
            "guardian_relation": "VARCHAR(60)",
            "birth_date": "DATE",
            "national_id": "VARCHAR(30) DEFAULT ''",
            "school_grade": "VARCHAR(120)",
            "current_memorization": "VARCHAR(250)",
        },
        "halaqa_account_requests": {
            "recipient_type": "VARCHAR(20) DEFAULT 'guardian'",
            "review_note": "TEXT DEFAULT ''",
            "guardian_relation": "VARCHAR(60)",
            "birth_date": "DATE",
            "national_id": "VARCHAR(30) DEFAULT ''",
            "school_grade": "VARCHAR(120)",
            "current_memorization": "VARCHAR(250)",
        },
    }
    with engine.begin() as connection:
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        for table, columns in additions.items():
            if table not in tables:
                continue
            existing = {column["name"] for column in inspector.get_columns(table)}
            for name, data_type in columns.items():
                if name not in existing:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {data_type}"))

        if 'users' in tables:
            connection.execute(text("UPDATE users SET account_type='guardian' WHERE role='halaqa_student' AND (account_type='' OR account_type IS NULL)"))
        if {"halaqat", "halaqa_supervisors"}.issubset(tables):
            connection.execute(text("""
                INSERT INTO halaqa_supervisors (halaqa_id, user_id, assigned_by, active, created_at)
                SELECT h.id, h.supervisor_id, h.supervisor_id, TRUE, CURRENT_TIMESTAMP
                FROM halaqat h
                WHERE h.supervisor_id IS NOT NULL
                  AND NOT EXISTS (
                    SELECT 1 FROM halaqa_supervisors hs
                    WHERE hs.halaqa_id = h.id AND hs.user_id = h.supervisor_id
                  )
            """))
