from datetime import datetime
from math import ceil
from typing import Optional
from .db import get_connection


def quantize_hours(hours: float, quantum: float) -> float:
    """Round hours up to the nearest quantum increment."""
    if quantum <= 0 or hours <= 0:
        return hours
    return ceil(hours / quantum) * quantum


class CustomerRepository:
    """CRUD operations for customers."""

    @staticmethod
    def create(name: str, color: str = '#3584e4') -> int:
        conn = get_connection()
        cur = conn.execute(
            "INSERT INTO customers (name, color) VALUES (?, ?)",
            (name, color)
        )
        conn.commit()
        cid = cur.lastrowid
        conn.close()
        return cid

    @staticmethod
    def get_all(active_only: bool = True) -> list[dict]:
        conn = get_connection()
        query = "SELECT * FROM customers"
        if active_only:
            query += " WHERE active = 1"
        query += " ORDER BY name"
        rows = conn.execute(query).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def get_by_id(customer_id: int) -> dict:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM customers WHERE id = ?", (customer_id,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def update(customer_id: int, **kwargs):
        conn = get_connection()
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        conn.execute(
            f"UPDATE customers SET {sets} WHERE id = ?",
            (*kwargs.values(), customer_id)
        )
        conn.commit()
        conn.close()

    @staticmethod
    def delete(customer_id: int):
        conn = get_connection()
        conn.execute("UPDATE customers SET active = 0 WHERE id = ?", (customer_id,))
        conn.commit()
        conn.close()


class ProjectRepository:
    """CRUD operations for projects."""

    @staticmethod
    def create(customer_id: int, name: str, hourly_rate: float = 0.0) -> int:
        conn = get_connection()
        cur = conn.execute(
            "INSERT INTO projects (customer_id, name, hourly_rate) VALUES (?, ?, ?)",
            (customer_id, name, hourly_rate)
        )
        conn.commit()
        pid = cur.lastrowid
        conn.close()
        return pid

    @staticmethod
    def get_all(active_only: bool = True) -> list[dict]:
        conn = get_connection()
        query = """SELECT p.*, c.name as customer_name, c.color
                   FROM projects p
                   JOIN customers c ON p.customer_id = c.id"""
        if active_only:
            query += " WHERE p.active = 1"
        query += " ORDER BY c.name, p.name"
        rows = conn.execute(query).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def get_by_customer(customer_id: int, active_only: bool = True) -> list[dict]:
        conn = get_connection()
        query = """SELECT p.*, c.name as customer_name, c.color
                   FROM projects p
                   JOIN customers c ON p.customer_id = c.id
                   WHERE p.customer_id = ?"""
        if active_only:
            query += " AND p.active = 1"
        query += " ORDER BY p.name"
        rows = conn.execute(query, (customer_id,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def get_by_id(project_id: int) -> dict:
        conn = get_connection()
        row = conn.execute(
            """SELECT p.*, c.name as customer_name, c.color
               FROM projects p
               JOIN customers c ON p.customer_id = c.id
               WHERE p.id = ?""",
            (project_id,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def update(project_id: int, **kwargs):
        conn = get_connection()
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        conn.execute(
            f"UPDATE projects SET {sets} WHERE id = ?",
            (*kwargs.values(), project_id)
        )
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

    _ENTRY_SELECT = """
        SELECT te.*, p.name as project_name, p.hourly_rate, p.time_quantum,
               c.name as customer_name, c.color, p.customer_id
        FROM time_entries te
        JOIN projects p ON te.project_id = p.id
        JOIN customers c ON p.customer_id = c.id
    """

    @staticmethod
    def start(project_id: int, note: str = '', description: str = '') -> int:
        conn = get_connection()
        cur = conn.execute(
            "INSERT INTO time_entries (project_id, start_time, note, description) VALUES (?, ?, ?, ?)",
            (project_id, datetime.now().isoformat(), note, description)
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
            f"""{TimeEntryRepository._ENTRY_SELECT}
                WHERE te.end_time IS NULL
                LIMIT 1"""
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def create_manual(project_id: int, start_time: str, end_time: str,
                      note: str = '', description: str = '') -> int:
        conn = get_connection()
        cur = conn.execute(
            """INSERT INTO time_entries (project_id, start_time, end_time, note, description)
               VALUES (?, ?, ?, ?, ?)""",
            (project_id, start_time, end_time, note, description)
        )
        conn.commit()
        eid = cur.lastrowid
        conn.close()
        return eid

    @staticmethod
    def get_entries(project_id: Optional[int] = None,
                    customer_id: Optional[int] = None,
                    start_date: Optional[str] = None,
                    end_date: Optional[str] = None,
                    include_running: bool = False) -> list[dict]:
        conn = get_connection()
        if include_running:
            query = f"""{TimeEntryRepository._ENTRY_SELECT}
                        WHERE 1=1"""
        else:
            query = f"""{TimeEntryRepository._ENTRY_SELECT}
                        WHERE te.end_time IS NOT NULL"""
        params = []
        if project_id:
            query += " AND te.project_id = ?"
            params.append(project_id)
        if customer_id:
            query += " AND p.customer_id = ?"
            params.append(customer_id)
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
    def get_entries_grouped_by_day(start_date: str, end_date: str) -> dict[str, list[dict]]:
        entries = TimeEntryRepository.get_entries(start_date=start_date, end_date=end_date, include_running=True)
        grouped = {}
        for entry in entries:
            day = entry['start_time'][:10]
            grouped.setdefault(day, []).append(entry)
        return grouped

    @staticmethod
    def update(entry_id: int, **kwargs):
        conn = get_connection()
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        conn.execute(
            f"UPDATE time_entries SET {sets} WHERE id = ?",
            (*kwargs.values(), entry_id)
        )
        conn.commit()
        conn.close()

    @staticmethod
    def delete(entry_id: int):
        conn = get_connection()
        conn.execute("DELETE FROM time_entries WHERE id = ?", (entry_id,))
        conn.commit()
        conn.close()

    @staticmethod
    def duplicate(entry_id: int) -> int:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM time_entries WHERE id = ?", (entry_id,)
        ).fetchone()
        if not row:
            conn.close()
            return -1
        entry = dict(row)
        # Use today's date but keep original times
        today = datetime.now().strftime('%Y-%m-%d')
        orig_start = datetime.fromisoformat(entry['start_time'])
        orig_end = datetime.fromisoformat(entry['end_time']) if entry['end_time'] else None
        new_start = f"{today}T{orig_start.strftime('%H:%M:%S')}"
        new_end = f"{today}T{orig_end.strftime('%H:%M:%S')}" if orig_end else None
        cur = conn.execute(
            """INSERT INTO time_entries (project_id, start_time, end_time, note, description)
               VALUES (?, ?, ?, ?, ?)""",
            (entry['project_id'], new_start, new_end,
             entry['note'], entry.get('description', ''))
        )
        conn.commit()
        eid = cur.lastrowid
        conn.close()
        return eid

    @staticmethod
    def get_summary(start_date: str, end_date: str,
                    customer_id: Optional[int] = None) -> list[dict]:
        entries = TimeEntryRepository.get_entries(
            start_date=start_date, end_date=end_date, customer_id=customer_id
        )
        projects = {}
        for e in entries:
            pid = e['project_id']
            if pid not in projects:
                projects[pid] = {
                    'project_name': e['project_name'],
                    'hourly_rate': e['hourly_rate'],
                    'time_quantum': e.get('time_quantum', 0.25),
                    'customer_name': e['customer_name'],
                    'color': e['color'],
                    'entry_count': 0,
                    'total_hours': 0.0,
                }
            st = datetime.fromisoformat(e['start_time'])
            et = datetime.fromisoformat(e['end_time'])
            raw_hours = (et - st).total_seconds() / 3600
            q = projects[pid]['time_quantum']
            projects[pid]['entry_count'] += 1
            projects[pid]['total_hours'] += quantize_hours(raw_hours, q)
        return sorted(projects.values(),
                      key=lambda x: (x['customer_name'], x['project_name']))

    @staticmethod
    def get_summary_by_customer(start_date: str, end_date: str,
                                customer_id: Optional[int] = None) -> list[dict]:
        entries = TimeEntryRepository.get_entries(
            start_date=start_date, end_date=end_date, customer_id=customer_id
        )
        customers = {}
        for e in entries:
            cname = e['customer_name']
            if cname not in customers:
                customers[cname] = {
                    'customer_name': cname,
                    'color': e['color'],
                    'entry_count': 0,
                    'total_hours': 0.0,
                    'total_amount': 0.0,
                }
            st = datetime.fromisoformat(e['start_time'])
            et = datetime.fromisoformat(e['end_time'])
            raw_hours = (et - st).total_seconds() / 3600
            q = e.get('time_quantum', 0.25)
            qh = quantize_hours(raw_hours, q)
            customers[cname]['entry_count'] += 1
            customers[cname]['total_hours'] += qh
            customers[cname]['total_amount'] += qh * (e['hourly_rate'] or 0)
        return sorted(customers.values(), key=lambda x: x['customer_name'])
