import sqlite3
from pathlib import Path

DB_PATH = Path.home() / ".local" / "share" / "timeworm" / "timeworm.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    color TEXT DEFAULT '#3584e4',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    hourly_rate REAL NOT NULL DEFAULT 0.0,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(id)
);

CREATE TABLE IF NOT EXISTS time_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP,
    note TEXT DEFAULT '',
    description TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE INDEX IF NOT EXISTS idx_entries_project ON time_entries(project_id);
CREATE INDEX IF NOT EXISTS idx_entries_start ON time_entries(start_time);
CREATE INDEX IF NOT EXISTS idx_projects_customer ON projects(customer_id);
"""


def get_connection() -> sqlite3.Connection:
    """Get a database connection, creating DB and tables if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _migrate_add_customers(conn: sqlite3.Connection):
    """Migrate old DB: add customers table and link existing projects."""
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='customers'"
    )
    if cursor.fetchone():
        return

    conn.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            color TEXT DEFAULT '#3584e4',
            active INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("INSERT INTO customers (name) VALUES ('Allgemein')")
    default_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Check if projects table already has customer_id
    cols = [row[1] for row in conn.execute("PRAGMA table_info(projects)")]
    if "customer_id" not in cols:
        conn.execute(
            f"ALTER TABLE projects ADD COLUMN customer_id INTEGER NOT NULL DEFAULT {default_id}"
        )

    # Check if time_entries has description column
    te_cols = [row[1] for row in conn.execute("PRAGMA table_info(time_entries)")]
    if "description" not in te_cols:
        conn.execute("ALTER TABLE time_entries ADD COLUMN description TEXT DEFAULT ''")

    # Drop old unique constraint on projects.name by recreating if needed
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_projects_customer ON projects(customer_id)"
    )

    conn.commit()


def init_db():
    """Initialize the database schema, running migrations if needed."""
    conn = get_connection()

    # Check if this is an existing DB that needs migration
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='projects'"
    )
    if cursor.fetchone():
        _migrate_add_customers(conn)
    else:
        conn.executescript(SCHEMA)
        conn.commit()

    conn.close()
