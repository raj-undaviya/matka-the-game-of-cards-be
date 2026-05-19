# migrate_sqlite_to_postgres.py

import sqlite3
import psycopg2

# ── Config ──────────────────────────────────────────────
SQLITE_DB = "db.sqlite3"  # tumhari .db file ka path

PG_CONFIG = {
    "host":     "localhost",
    "port":     5432,
    "database": "matka_db",
    "user":     "postgres",
    "password": "raaj@123"
}
# ────────────────────────────────────────────────────────

# SQLite → PostgreSQL type mapping
TYPE_MAP = {
    "INTEGER":  "INTEGER",
    "REAL":     "DOUBLE PRECISION",
    "TEXT":     "TEXT",
    "BLOB":     "BYTEA",
    "BOOLEAN":  "BOOLEAN",
    "DATETIME": "TIMESTAMP",
    "DATE":     "DATE",
    "NUMERIC":  "NUMERIC",
    "VARCHAR":  "TEXT",
    "":         "TEXT",
}

# Yeh boolean column names Django me hote hain
BOOLEAN_COLUMN_NAMES = {
    "is_superuser", "is_staff", "is_active", "is_verified"
}


def get_pg_type(sqlite_type: str) -> str:
    upper = sqlite_type.upper().split("(")[0].strip()
    return TYPE_MAP.get(upper, "TEXT")


def get_pg_type_for_col(col) -> str:
    """Type + column name dono se decide karo."""
    if col["name"].lower() in BOOLEAN_COLUMN_NAMES:
        return "BOOLEAN"
    if col["name"].lower().startswith("is_"):
        return "BOOLEAN"
    return get_pg_type(col["type"])


def convert_row(row, columns):
    """SQLite 0/1 integers ko Python bool me convert karo."""
    result = []
    for col, val in zip(columns, tuple(row)):
        pg_type  = get_pg_type_for_col(col)
        is_bool  = (pg_type == "BOOLEAN")

        if is_bool and val is not None:
            result.append(bool(val))
        else:
            result.append(val)
    return tuple(result)


def migrate():
    sqlite_conn = sqlite3.connect(SQLITE_DB)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cur  = sqlite_conn.cursor()

    pg_conn = psycopg2.connect(**PG_CONFIG)
    pg_cur  = pg_conn.cursor()

    # Sabhi tables ki list lo
    sqlite_cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in sqlite_cur.fetchall()]
    print(f"✓ {len(tables)} tables mili: {tables}")

    for table in tables:
        print(f"\n── Table: {table} ──")

        # Column info SQLite se
        sqlite_cur.execute(f"PRAGMA table_info({table})")
        columns = sqlite_cur.fetchall()

        # CREATE TABLE banao PostgreSQL ke liye
        col_defs = []
        for col in columns:
            name    = col["name"]
            pg_type = get_pg_type_for_col(col)   # ← updated
            pk      = " PRIMARY KEY" if col["pk"] else ""
            notnull = " NOT NULL"    if col["notnull"] and not col["pk"] else ""
            col_defs.append(f'"{name}" {pg_type}{pk}{notnull}')

        create_stmt = f'CREATE TABLE IF NOT EXISTS "{table}" ({", ".join(col_defs)});'
        pg_cur.execute(create_stmt)
        pg_conn.commit()
        print(f"  ✓ Table create hui")

        # Saara data SQLite se lo
        sqlite_cur.execute(f'SELECT * FROM "{table}"')
        rows = sqlite_cur.fetchall()

        if not rows:
            print(f"  ⚠ Koi data nahi mila")
            continue

        # Batch insert PostgreSQL me
        col_names    = [col["name"] for col in columns]
        placeholders = ", ".join(["%s"] * len(col_names))
        col_list     = ", ".join([f'"{c}"' for c in col_names])
        insert_stmt  = f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders}) ON CONFLICT DO NOTHING'

        # Boolean conversion
        data = [convert_row(row, columns) for row in rows]

        pg_cur.executemany(insert_stmt, data)
        pg_conn.commit()
        print(f"  ✓ {len(data)} rows insert hui")

    # Verification
    print("\n── Verification ──")
    for table in tables:
        sqlite_cur.execute(f'SELECT COUNT(*) FROM "{table}"')
        s_count = sqlite_cur.fetchone()[0]
        pg_cur.execute(f'SELECT COUNT(*) FROM "{table}"')
        p_count = pg_cur.fetchone()[0]
        status = "✓" if s_count == p_count else "✗ MISMATCH"
        print(f"  {status} {table}: SQLite={s_count}, Postgres={p_count}")

    sqlite_conn.close()
    pg_cur.close()
    pg_conn.close()
    print("\n✅ Migration complete!")


if __name__ == "__main__":
    migrate()