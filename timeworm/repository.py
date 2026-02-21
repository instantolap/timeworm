from datetime import datetime, timedelta
from typing import Optional
from .db import get_connection, init_db


class ProjectRepository:
    """CRUD operations for projects."""

    @staticmethod
    def create(name: str, hourly_rate: float = 0.0, color: str = '#3584e4') -> int:
        conn = get_connection()
        cur = conn.execute(
            "INSERT INTO projects (name, hourly_rate, color) VALUES (?, ?, ?)",
            (name, hourly_rate, color)
        )
        conn.commit()
        pid = cur.lastrowid
        conn.close()
        return pid

    @staticmethod
    def get_all(active_only: bool = True) -> list:
        conn = get_connection()
        query = "SELECT * FROM projects"
        if active_only:
            query += " WHERE active = 1"
        query += " ORDER BY name"
        rows = conn.execute(query).fetchall()
        conn.close()
        return rows

    @staticmethod
    def update(project_id: int, **kwargs):
        conn = get_connection()
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        conn.execute(f"UPDATE projects SET {sets} WHERE id = ?",
                     (*kwargs.values(), project_id))
        conn.commit()
        conn.close()

    @staticmethod
    def delete(project_id: int):
        conn = get_connection()
        conn.execute("UPDATE projects SET active = 0 WHERE id = ?", (project_id,))
        conn.commit()
        conn.close()


class TimeEntryRepository:
    """CRUD operations for time entries."""

    @staticmethod
    def start(project_id: int, note: str = '') -> int:
        conn = get_connection()
        cur = conn.execute(
            "INSERT INTO time_entries (project_id, start_time, note) VALUES (?, ?, ?)",
            (project_id, datetime.now().isoformat(), note)
        )
        conn.commit()
        eid = cur.lastrowid
        conn.close()
        return eid

    @staticmethod
    def stop(entry_id: int):
        conn = get_connection()
        conn.execute(
            "UPDATE time_entries SET end_time = ? WHERE id = ? AND end_time IS NULL",
            (datetime.now().isoformat(), entry_id)
        )
        conn.commit()
        conn.close()

    @staticmethod
    def stop_running():
        """Stop any currently running timer."""
        conn = get_connection()
        conn.execute(
            "UPDATE time_entries SET end_time = ? WHERE end_time IS NULL",
            (datetime.now().isoformat(),)
        )
        conn.commit()
        conn.close()

    @staticmethod
    def get_running() -> Optional[dict]:
        conn = get_connection()
        row = conn.execute(
            """SELECT te.*, p.name as project_name, p.hourly_rate, p.color
               FROM time_entries te
               JOIN projects p ON te.project_id = p.id
               WHERE te.end_time IS NULL
               LIMIT 1"""
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def get_entries(project_id: Optional[int] = None,
                    start_date: Optional[str] = None,
                    end_date: Optional[str] = None) -> list:
        conn = get_connection()
        query = """SELECT te.*, p.name as project_name, p.hourly_rate, p.color
                   FROM time_entries te
                   JOIN projects p ON te.project_id = p.id
                   WHERE te.end_time IS NOT NULL"""
        params = []
        if project_id:
            query += " AND te.project_id = ?"
            params.append(project_id)
        if start_date:
            query += " AND te.start_time >= ?"
            params.append(start_date)
        if end_date:
            query += " AND te.start_time <= ?"
            params.append(end_date)
        query += " ORDER BY te.start_time DESC"
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def create_manual(project_id: int, start_time: str, end_time: str, note: str = '') -> int:
        conn = get_connection()
        cur = conn.execute(
            "INSERT INTO time_entries (project_id, start_time, end_time, note) VALUES (?, ?, ?, ?)",
            (project_id, start_time, end_time, note)
        )
        conn.commit()
        eid = cur.lastrowid
        conn.close()
        return eid

    @staticmethod
    def update(entry_id: int, **kwargs):
        conn = get_connection()
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        conn.execute(f"UPDATE time_entries SET {sets} WHERE id = ?",
                     (*kwargs.values(), entry_id))
        conn.commit()
        conn.close()

    @staticmethod
    def delete(entry_id: int):
        conn = get_connection()
        conn.execute("DELETE FROM time_entries WHERE id = ?", (entry_id,))
        conn.commit()
        conn.close()

    @staticmethod
    def get_summary(start_date: str, end_date: str) -> list:
        """Get hours and earnings summary grouped by project."""
        conn = get_connection()
        rows = conn.execute("""
            SELECT p.name, p.hourly_rate, p.color,
                   COUNT(te.id) as entry_count,
                   SUM(
                       (julianday(te.end_time) - julianday(te.start_time)) * 24
                   ) as total_hours
            FROM time_entries te
            JOIN projects p ON te.project_id = p.id
            WHERE te.end_time IS NOT NULL
              AND te.start_time >= ? AND te.start_time <= ?
            GROUP BY p.id
            ORDER BY total_hours DESC
        """, (start_date, end_date)).fetchall()
        conn.close()
        return [dict(r) for r in rows]
