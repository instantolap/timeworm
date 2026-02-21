#!/usr/bin/env python3
"""TimeWorm MCP Server - Time tracking via Claude/MCP.

Reads and writes the same SQLite DB as the TimeWorm GTK app.
"""
import json
import sys
import os

# Add parent dir so we can import timeworm modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from math import ceil
from timeworm.db import get_connection, init_db
from timeworm.repository import (
    CustomerRepository, ProjectRepository, TimeEntryRepository, quantize_hours
)

# ── MCP Protocol helpers ──────────────────────────────────────────

def send_response(id, result):
    msg = {"jsonrpc": "2.0", "id": id, "result": result}
    out = json.dumps(msg)
    sys.stdout.write(f"Content-Length: {len(out)}\r\n\r\n{out}")
    sys.stdout.flush()

def send_error(id, code, message):
    msg = {"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}
    out = json.dumps(msg)
    sys.stdout.write(f"Content-Length: {len(out)}\r\n\r\n{out}")
    sys.stdout.flush()

def read_message():
    headers = {}
    while True:
        line = sys.stdin.readline()
        if not line or line == "\r\n" or line == "\n":
            break
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip()] = v.strip()
    length = int(headers.get("Content-Length", 0))
    if length == 0:
        return None
    body = sys.stdin.read(length)
    return json.loads(body)

# ── Tool definitions ──────────────────────────────────────────────

TOOLS = [
    {
        "name": "tw_list_customers",
        "description": "List all active customers.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "tw_list_projects",
        "description": "List all active projects, optionally filtered by customer name.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer": {"type": "string", "description": "Filter by customer name (partial match)"}
            }
        }
    },
    {
        "name": "tw_start_timer",
        "description": "Start a live timer for a project. Stops any running timer first.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Project name (partial match)"},
                "description": {"type": "string", "description": "What are you working on?"}
            },
            "required": ["project"]
        }
    },
    {
        "name": "tw_stop_timer",
        "description": "Stop the currently running timer.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "tw_status",
        "description": "Show current timer status and today's entries.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "tw_log_time",
        "description": "Log a completed time entry (manual booking).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Project name (partial match)"},
                "hours": {"type": "number", "description": "Duration in hours (e.g. 1.5)"},
                "description": {"type": "string", "description": "What was done"},
                "date": {"type": "string", "description": "Date YYYY-MM-DD (default: today)"},
                "start_time": {"type": "string", "description": "Start HH:MM (default: 09:00)"},
                "note": {"type": "string", "description": "Additional notes"}
            },
            "required": ["project", "hours"]
        }
    },
    {
        "name": "tw_summary",
        "description": "Get time/revenue summary for a month, optionally filtered by customer.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "month": {"type": "integer", "description": "Month 1-12 (default: current)"},
                "year": {"type": "integer", "description": "Year (default: current)"},
                "customer": {"type": "string", "description": "Filter by customer name"}
            }
        }
    },
    {
        "name": "tw_entries",
        "description": "List time entries for a date range.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Number of past days to show (default: 7)"},
                "customer": {"type": "string", "description": "Filter by customer name"},
                "project": {"type": "string", "description": "Filter by project name"}
            }
        }
    },
]

# ── Tool implementations ──────────────────────────────────────────

def find_project(name: str) -> dict | None:
    """Find project by partial name match (case-insensitive)."""
    projects = ProjectRepository.get_all()
    name_lower = name.lower()
    # Exact match first
    for p in projects:
        if p['name'].lower() == name_lower:
            return p
    # Partial match
    for p in projects:
        if name_lower in p['name'].lower():
            return p
    # Try customer+project combo
    for p in projects:
        combo = f"{p['customer_name']} {p['name']}".lower()
        if name_lower in combo:
            return p
    return None

def find_customer_id(name: str) -> int | None:
    """Find customer by partial name match."""
    customers = CustomerRepository.get_all()
    name_lower = name.lower()
    for c in customers:
        if c['name'].lower() == name_lower:
            return c['id']
    for c in customers:
        if name_lower in c['name'].lower():
            return c['id']
    return None

def handle_list_customers(args):
    customers = CustomerRepository.get_all()
    lines = []
    for c in customers:
        projects = ProjectRepository.get_by_customer(c['id'])
        pnames = ", ".join(f"{p['name']} ({p['hourly_rate']}€/h)" for p in projects)
        lines.append(f"• {c['name']}: {pnames or 'keine Projekte'}")
    return "\n".join(lines) or "Keine Kunden vorhanden."

def handle_list_projects(args):
    projects = ProjectRepository.get_all()
    customer_filter = args.get("customer", "").lower()
    if customer_filter:
        projects = [p for p in projects if customer_filter in p['customer_name'].lower()]
    lines = []
    for p in projects:
        q = p.get('time_quantum', 0.25)
        lines.append(f"• {p['name']} [{p['customer_name']}] — {p['hourly_rate']}€/h, Quantum: {q}h")
    return "\n".join(lines) or "Keine Projekte gefunden."

def handle_start_timer(args):
    project = find_project(args["project"])
    if not project:
        return f"❌ Projekt '{args['project']}' nicht gefunden."
    TimeEntryRepository.stop_running()
    desc = args.get("description", "")
    eid = TimeEntryRepository.start(project['id'], description=desc)
    return f"⏱ Timer gestartet: {project['name']} ({project['customer_name']})\nBeschreibung: {desc or '–'}\nEntry ID: {eid}"

def handle_stop_timer(args):
    running = TimeEntryRepository.get_running()
    if not running:
        return "Kein Timer läuft."
    start = datetime.fromisoformat(running['start_time'])
    elapsed = datetime.now() - start
    mins = int(elapsed.total_seconds() / 60)
    q = running.get('time_quantum', 0.25) or 0.25
    qh = quantize_hours(elapsed.total_seconds() / 3600, q)
    amount = qh * (running['hourly_rate'] or 0)
    TimeEntryRepository.stop(running['id'])
    return (f"⏹ Timer gestoppt: {running['project_name']} ({running['customer_name']})\n"
            f"Dauer: {mins}min → quantisiert: {qh:.2f}h\n"
            f"Betrag: {amount:.2f}€")

def handle_status(args):
    running = TimeEntryRepository.get_running()
    lines = []
    if running:
        start = datetime.fromisoformat(running['start_time'])
        elapsed = datetime.now() - start
        mins = int(elapsed.total_seconds() / 60)
        desc = running.get('description', '') or ''
        lines.append(f"⏱ LÄUFT: {running['project_name']} ({running['customer_name']}) — {mins}min")
        if desc:
            lines.append(f"  Beschreibung: {desc}")
        lines.append("")
    # Today's entries
    today = datetime.now().strftime('%Y-%m-%d')
    entries = TimeEntryRepository.get_entries(
        start_date=f"{today}T00:00:00",
        end_date=f"{today}T23:59:59",
        include_running=True
    )
    total_h = 0
    total_amount = 0
    lines.append(f"📅 Heute ({today}):")
    for e in entries:
        if e['end_time']:
            st = datetime.fromisoformat(e['start_time'])
            et = datetime.fromisoformat(e['end_time'])
            raw_h = (et - st).total_seconds() / 3600
            q = e.get('time_quantum', 0.25) or 0.25
            h = quantize_hours(raw_h, q)
            total_h += h
            total_amount += h * (e['hourly_rate'] or 0)
            desc = e.get('description', '') or ''
            lines.append(f"  • {e['project_name']}: {h:.2f}h = {h * (e['hourly_rate'] or 0):.2f}€{' — ' + desc if desc else ''}")
        else:
            lines.append(f"  • {e['project_name']}: ⏱ läuft...")
    if not entries:
        lines.append("  Keine Einträge.")
    else:
        lines.append(f"  ─────────")
        lines.append(f"  Gesamt: {total_h:.2f}h = {total_amount:.2f}€")
    return "\n".join(lines)

def handle_log_time(args):
    project = find_project(args["project"])
    if not project:
        return f"❌ Projekt '{args['project']}' nicht gefunden."
    hours = args["hours"]
    date = args.get("date", datetime.now().strftime('%Y-%m-%d'))
    start_hm = args.get("start_time", "09:00")
    desc = args.get("description", "")
    note = args.get("note", "")
    start_dt = f"{date}T{start_hm}:00"
    end_mins = int(hours * 60)
    end_dt_obj = datetime.fromisoformat(start_dt) + timedelta(minutes=end_mins)
    end_dt = end_dt_obj.isoformat()
    eid = TimeEntryRepository.create_manual(project['id'], start_dt, end_dt, note=note, description=desc)
    q = project.get('time_quantum', 0.25) or 0.25
    qh = quantize_hours(hours, q)
    amount = qh * (project['hourly_rate'] or 0)
    return (f"✅ Gebucht: {project['name']} ({project['customer_name']})\n"
            f"Datum: {date}, {start_hm} – {end_dt_obj.strftime('%H:%M')}\n"
            f"Dauer: {hours}h → quantisiert: {qh:.2f}h\n"
            f"Betrag: {amount:.2f}€\n"
            f"Beschreibung: {desc or '–'}")

def handle_summary(args):
    now = datetime.now()
    month = args.get("month", now.month)
    year = args.get("year", now.year)
    start = f"{year:04d}-{month:02d}-01T00:00:00"
    if month == 12:
        end = f"{year + 1:04d}-01-01T00:00:00"
    else:
        end = f"{year:04d}-{month + 1:02d}-01T00:00:00"
    customer_id = None
    cust_name = args.get("customer")
    if cust_name:
        customer_id = find_customer_id(cust_name)
        if customer_id is None:
            return f"❌ Kunde '{cust_name}' nicht gefunden."
    MONTHS_DE = ["", "Januar", "Februar", "März", "April", "Mai", "Juni",
                 "Juli", "August", "September", "Oktober", "November", "Dezember"]
    lines = [f"📊 {MONTHS_DE[month]} {year}" + (f" — {cust_name}" if cust_name else ""), ""]
    customer_summary = TimeEntryRepository.get_summary_by_customer(start, end, customer_id=customer_id)
    project_summary = TimeEntryRepository.get_summary(start, end, customer_id=customer_id)
    if not customer_summary:
        return f"Keine Einträge in {MONTHS_DE[month]} {year}."
    projects_by_cust = {}
    for p in project_summary:
        projects_by_cust.setdefault(p['customer_name'], []).append(p)
    grand_h = 0
    grand_amount = 0
    for cs in customer_summary:
        cn = cs['customer_name']
        lines.append(f"🏢 {cn}: {cs['total_hours']:.2f}h = {cs['total_amount']:.2f}€")
        grand_h += cs['total_hours']
        grand_amount += cs['total_amount']
        for p in projects_by_cust.get(cn, []):
            ph = p['total_hours']
            pa = ph * (p['hourly_rate'] or 0)
            lines.append(f"   • {p['project_name']}: {ph:.2f}h × {p['hourly_rate']}€ = {pa:.2f}€ ({p['entry_count']} Einträge)")
        lines.append("")
    lines.append(f"═══════════════════════════")
    lines.append(f"GESAMT: {grand_h:.2f}h = {grand_amount:.2f}€")
    return "\n".join(lines)

def handle_entries(args):
    days = args.get("days", 7)
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=days)
    customer_id = None
    if args.get("customer"):
        customer_id = find_customer_id(args["customer"])
    project_id = None
    if args.get("project"):
        p = find_project(args["project"])
        if p:
            project_id = p['id']
    entries = TimeEntryRepository.get_entries(
        project_id=project_id,
        customer_id=customer_id,
        start_date=start_dt.isoformat(),
        end_date=end_dt.isoformat()
    )
    if not entries:
        return f"Keine Einträge in den letzten {days} Tagen."
    lines = [f"📋 Einträge der letzten {days} Tage:", ""]
    current_day = None
    day_total_h = 0
    for e in entries:
        day = e['start_time'][:10]
        if day != current_day:
            if current_day:
                lines.append(f"  Tagesgesamt: {day_total_h:.2f}h")
                lines.append("")
            current_day = day
            day_total_h = 0
            lines.append(f"📅 {day}:")
        st = datetime.fromisoformat(e['start_time'])
        et = datetime.fromisoformat(e['end_time'])
        raw_h = (et - st).total_seconds() / 3600
        q = e.get('time_quantum', 0.25) or 0.25
        h = quantize_hours(raw_h, q)
        day_total_h += h
        desc = e.get('description', '') or ''
        lines.append(f"  • {st.strftime('%H:%M')}–{et.strftime('%H:%M')} {e['project_name']} ({e['customer_name']}): {h:.2f}h{' — ' + desc if desc else ''}")
    if current_day:
        lines.append(f"  Tagesgesamt: {day_total_h:.2f}h")
    return "\n".join(lines)

TOOL_HANDLERS = {
    "tw_list_customers": handle_list_customers,
    "tw_list_projects": handle_list_projects,
    "tw_start_timer": handle_start_timer,
    "tw_stop_timer": handle_stop_timer,
    "tw_status": handle_status,
    "tw_log_time": handle_log_time,
    "tw_summary": handle_summary,
    "tw_entries": handle_entries,
}

# ── Main MCP loop ─────────────────────────────────────────────────

def main():
    init_db()
    while True:
        msg = read_message()
        if msg is None:
            break
        method = msg.get("method")
        id = msg.get("id")
        params = msg.get("params", {})
        if method == "initialize":
            send_response(id, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "timeworm", "version": "1.0.0"}
            })
        elif method == "notifications/initialized":
            pass  # No response needed
        elif method == "tools/list":
            send_response(id, {"tools": TOOLS})
        elif method == "tools/call":
            tool_name = params.get("name")
            tool_args = params.get("arguments", {})
            handler = TOOL_HANDLERS.get(tool_name)
            if handler:
                try:
                    result_text = handler(tool_args)
                    send_response(id, {
                        "content": [{"type": "text", "text": result_text}]
                    })
                except Exception as e:
                    send_response(id, {
                        "content": [{"type": "text", "text": f"❌ Fehler: {str(e)}"}],
                        "isError": True
                    })
            else:
                send_error(id, -32601, f"Unknown tool: {tool_name}")
        elif method == "ping":
            send_response(id, {})
        else:
            if id is not None:
                send_error(id, -32601, f"Unknown method: {method}")

if __name__ == "__main__":
    main()