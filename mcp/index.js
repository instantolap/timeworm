#!/usr/bin/env node
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { CallToolRequestSchema, ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";
import Database from "better-sqlite3";
import { homedir } from "os";
import { join } from "path";
import { mkdirSync, existsSync } from "fs";

// ── Database ─────────────────────────────────────────────────────

const DB_DIR = join(homedir(), ".local", "share", "timeworm");
const DB_PATH = join(DB_DIR, "timeworm.db");

let db;

function getDb() {
  if (!db) {
    if (!existsSync(DB_DIR)) mkdirSync(DB_DIR, { recursive: true });
    db = new Database(DB_PATH);
    db.pragma("journal_mode = WAL");
    db.pragma("foreign_keys = ON");
  }
  return db;
}

function quantize(hours, quantum) {
  if (quantum <= 0 || hours <= 0) return hours;
  return Math.ceil(hours / quantum) * quantum;
}

function isoNow() {
  return new Date().toISOString().replace("Z", "").replace("T", "T").slice(0, 19);
}

function toLocal(isoStr) {
  if (!isoStr) return null;
  const d = new Date(isoStr);
  const pad = n => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

function nowLocal() {
  return toLocal(new Date().toISOString());
}
// ── Queries ──────────────────────────────────────────────────────

const ENTRY_SELECT = `
  SELECT te.*, p.name as project_name, p.hourly_rate, p.time_quantum,
         c.name as customer_name, c.color, p.customer_id
  FROM time_entries te
  JOIN projects p ON te.project_id = p.id
  JOIN customers c ON p.customer_id = c.id
`;

function findProject(name) {
  const d = getDb();
  const projects = d.prepare(`
    SELECT p.*, c.name as customer_name FROM projects p
    JOIN customers c ON p.customer_id = c.id WHERE p.active = 1
  `).all();
  const nl = name.toLowerCase();
  return projects.find(p => p.name.toLowerCase() === nl)
    || projects.find(p => p.name.toLowerCase().includes(nl))
    || projects.find(p => `${p.customer_name} ${p.name}`.toLowerCase().includes(nl))
    || null;
}

function findCustomerId(name) {
  const d = getDb();
  const customers = d.prepare("SELECT * FROM customers WHERE active = 1").all();
  const nl = name.toLowerCase();
  return (customers.find(c => c.name.toLowerCase() === nl)
    || customers.find(c => c.name.toLowerCase().includes(nl)))?.id || null;
}

// ── Tool handlers ────────────────────────────────────────────────

function handleListCustomers() {
  const d = getDb();
  const customers = d.prepare("SELECT * FROM customers WHERE active = 1 ORDER BY name").all();
  const lines = customers.map(c => {
    const projects = d.prepare(
      "SELECT name, hourly_rate FROM projects WHERE customer_id = ? AND active = 1"
    ).all(c.id);
    const pStr = projects.map(p => `${p.name} (${p.hourly_rate}€/h)`).join(", ");
    return `• ${c.name}: ${pStr || "keine Projekte"}`;
  });
  return lines.join("\n") || "Keine Kunden vorhanden.";
}

function handleListProjects(args) {
  const d = getDb();
  let projects = d.prepare(`
    SELECT p.*, c.name as customer_name FROM projects p
    JOIN customers c ON p.customer_id = c.id WHERE p.active = 1 ORDER BY c.name, p.name
  `).all();
  if (args.customer) {
    const f = args.customer.toLowerCase();
    projects = projects.filter(p => p.customer_name.toLowerCase().includes(f));
  }
  return projects.map(p =>
    `• ${p.name} [${p.customer_name}] — ${p.hourly_rate}€/h, Quantum: ${p.time_quantum || 0.25}h`
  ).join("\n") || "Keine Projekte gefunden.";
}

function handleStartTimer(args) {
  const project = findProject(args.project);
  if (!project) return `❌ Projekt '${args.project}' nicht gefunden.`;
  const d = getDb();
  const now = nowLocal();
  // Stop running timers
  d.prepare("UPDATE time_entries SET end_time = ? WHERE end_time IS NULL").run(now);
  const desc = args.description || "";
  const r = d.prepare(
    "INSERT INTO time_entries (project_id, start_time, note, description) VALUES (?, ?, '', ?)"
  ).run(project.id, now, desc);
  return `⏱ Timer gestartet: ${project.name} (${project.customer_name})\nBeschreibung: ${desc || "–"}\nEntry ID: ${r.lastInsertRowid}`;
}

function handleStopTimer() {
  const d = getDb();
  const running = d.prepare(`${ENTRY_SELECT} WHERE te.end_time IS NULL LIMIT 1`).get();
  if (!running) return "Kein Timer läuft.";
  const now = nowLocal();
  const start = new Date(running.start_time);
  const elapsed = (new Date(now) - start) / 1000;
  const mins = Math.floor(elapsed / 60);
  const q = running.time_quantum || 0.25;
  const qh = quantize(elapsed / 3600, q);
  const amount = qh * (running.hourly_rate || 0);
  d.prepare("UPDATE time_entries SET end_time = ? WHERE id = ?").run(now, running.id);
  return `⏹ Timer gestoppt: ${running.project_name} (${running.customer_name})\nDauer: ${mins}min → quantisiert: ${qh.toFixed(2)}h\nBetrag: ${amount.toFixed(2)}€`;
}
function handleStatus() {
  const d = getDb();
  const running = d.prepare(`${ENTRY_SELECT} WHERE te.end_time IS NULL LIMIT 1`).get();
  const lines = [];
  if (running) {
    const elapsed = Math.floor((Date.now() - new Date(running.start_time).getTime()) / 60000);
    lines.push(`⏱ LÄUFT: ${running.project_name} (${running.customer_name}) — ${elapsed}min`);
    if (running.description) lines.push(`  Beschreibung: ${running.description}`);
    lines.push("");
  }
  const today = nowLocal().slice(0, 10);
  const entries = d.prepare(
    `${ENTRY_SELECT} WHERE te.start_time >= ? AND te.start_time <= ? ORDER BY te.start_time DESC`
  ).all(`${today}T00:00:00`, `${today}T23:59:59`);
  let totalH = 0, totalAmount = 0;
  lines.push(`📅 Heute (${today}):`);
  for (const e of entries) {
    if (e.end_time) {
      const rawH = (new Date(e.end_time) - new Date(e.start_time)) / 3600000;
      const h = quantize(rawH, e.time_quantum || 0.25);
      totalH += h;
      totalAmount += h * (e.hourly_rate || 0);
      const desc = e.description ? ` — ${e.description}` : "";
      lines.push(`  • ${e.project_name}: ${h.toFixed(2)}h = ${(h * (e.hourly_rate || 0)).toFixed(2)}€${desc}`);
    } else {
      lines.push(`  • ${e.project_name}: ⏱ läuft...`);
    }
  }
  if (!entries.length) lines.push("  Keine Einträge.");
  else {
    lines.push("  ─────────");
    lines.push(`  Gesamt: ${totalH.toFixed(2)}h = ${totalAmount.toFixed(2)}€`);
  }
  return lines.join("\n");
}

function handleLogTime(args) {
  const project = findProject(args.project);
  if (!project) return `❌ Projekt '${args.project}' nicht gefunden.`;
  const date = args.date || nowLocal().slice(0, 10);
  const startHm = args.start_time || "09:00";
  const startDt = `${date}T${startHm}:00`;
  const endMs = new Date(startDt).getTime() + args.hours * 3600000;
  const endDt = toLocal(new Date(endMs).toISOString());
  const d = getDb();
  const r = d.prepare(
    "INSERT INTO time_entries (project_id, start_time, end_time, note, description) VALUES (?, ?, ?, ?, ?)"
  ).run(project.id, startDt, endDt, args.note || "", args.description || "");
  const q = project.time_quantum || 0.25;
  const qh = quantize(args.hours, q);
  const amount = qh * (project.hourly_rate || 0);
  const endHm = endDt.slice(11, 16);
  return `✅ Gebucht: ${project.name} (${project.customer_name})\nDatum: ${date}, ${startHm} – ${endHm}\nDauer: ${args.hours}h → quantisiert: ${qh.toFixed(2)}h\nBetrag: ${amount.toFixed(2)}€\nBeschreibung: ${args.description || "–"}`;
}

function handleSummary(args) {
  const now = new Date();
  const month = args.month || now.getMonth() + 1;
  const year = args.year || now.getFullYear();
  const pad = n => String(n).padStart(2, "0");
  const start = `${year}-${pad(month)}-01T00:00:00`;
  const endM = month === 12 ? `${year + 1}-01-01T00:00:00` : `${year}-${pad(month + 1)}-01T00:00:00`;
  const MONTHS = ["","Januar","Februar","März","April","Mai","Juni","Juli","August","September","Oktober","November","Dezember"];

  let custFilter = "";
  const params = [start, endM];
  if (args.customer) {
    const cid = findCustomerId(args.customer);
    if (!cid) return `❌ Kunde '${args.customer}' nicht gefunden.`;
    custFilter = " AND p.customer_id = ?";
    params.push(cid);
  }

  const d = getDb();
  const entries = d.prepare(
    `${ENTRY_SELECT} WHERE te.end_time IS NOT NULL AND te.start_time >= ? AND te.start_time < ?${custFilter} ORDER BY c.name, p.name`
  ).all(...params);

  if (!entries.length) return `Keine Einträge in ${MONTHS[month]} ${year}.`;

  const customers = {};
  const projects = {};
  for (const e of entries) {
    const rawH = (new Date(e.end_time) - new Date(e.start_time)) / 3600000;
    const qh = quantize(rawH, e.time_quantum || 0.25);
    const cn = e.customer_name;
    if (!customers[cn]) customers[cn] = { hours: 0, amount: 0, color: e.color };
    customers[cn].hours += qh;
    customers[cn].amount += qh * (e.hourly_rate || 0);
    const pk = `${cn}|${e.project_name}`;
    if (!projects[pk]) projects[pk] = { customer: cn, name: e.project_name, hours: 0, rate: e.hourly_rate, count: 0 };
    projects[pk].hours += qh;
    projects[pk].count++;
  }

  const lines = [`📊 ${MONTHS[month]} ${year}${args.customer ? ` — ${args.customer}` : ""}`, ""];
  let grandH = 0, grandA = 0;
  for (const [cn, cs] of Object.entries(customers).sort()) {
    lines.push(`🏢 ${cn}: ${cs.hours.toFixed(2)}h = ${cs.amount.toFixed(2)}€`);
    grandH += cs.hours; grandA += cs.amount;
    for (const p of Object.values(projects).filter(p => p.customer === cn).sort((a,b) => a.name.localeCompare(b.name))) {
      const pa = p.hours * (p.rate || 0);
      lines.push(`   • ${p.name}: ${p.hours.toFixed(2)}h × ${p.rate}€ = ${pa.toFixed(2)}€ (${p.count} Einträge)`);
    }
    lines.push("");
  }
  lines.push("═══════════════════════════");
  lines.push(`GESAMT: ${grandH.toFixed(2)}h = ${grandA.toFixed(2)}€`);
  return lines.join("\n");
}
function handleEntries(args) {
  const days = args.days || 7;
  const now = new Date();
  const startDt = new Date(now.getTime() - days * 86400000);
  const startStr = toLocal(startDt.toISOString());
  const endStr = nowLocal();
  const d = getDb();

  let custFilter = "", projFilter = "";
  const params = [startStr, endStr];
  if (args.customer) {
    const cid = findCustomerId(args.customer);
    if (cid) { custFilter = " AND p.customer_id = ?"; params.push(cid); }
  }
  if (args.project) {
    const p = findProject(args.project);
    if (p) { projFilter = " AND te.project_id = ?"; params.push(p.id); }
  }

  const entries = d.prepare(
    `${ENTRY_SELECT} WHERE te.end_time IS NOT NULL AND te.start_time >= ? AND te.start_time <= ?${custFilter}${projFilter} ORDER BY te.start_time DESC`
  ).all(...params);

  if (!entries.length) return `Keine Einträge in den letzten ${days} Tagen.`;

  const lines = [`📋 Einträge der letzten ${days} Tage:`, ""];
  let currentDay = null, dayH = 0;
  for (const e of entries) {
    const day = e.start_time.slice(0, 10);
    if (day !== currentDay) {
      if (currentDay) { lines.push(`  Tagesgesamt: ${dayH.toFixed(2)}h`); lines.push(""); }
      currentDay = day; dayH = 0;
      lines.push(`📅 ${day}:`);
    }
    const rawH = (new Date(e.end_time) - new Date(e.start_time)) / 3600000;
    const h = quantize(rawH, e.time_quantum || 0.25);
    dayH += h;
    const desc = e.description ? ` — ${e.description}` : "";
    const st = e.start_time.slice(11, 16);
    const et = e.end_time.slice(11, 16);
    lines.push(`  • ${st}–${et} ${e.project_name} (${e.customer_name}): ${h.toFixed(2)}h${desc}`);
  }
  if (currentDay) lines.push(`  Tagesgesamt: ${dayH.toFixed(2)}h`);
  return lines.join("\n");
}

// ── Tool definitions ─────────────────────────────────────────────

const TOOLS = [
  {
    name: "tw_list_customers",
    description: "List all active customers with their projects.",
    inputSchema: { type: "object", properties: {} }
  },
  {
    name: "tw_list_projects",
    description: "List all active projects, optionally filtered by customer name.",
    inputSchema: {
      type: "object",
      properties: {
        customer: { type: "string", description: "Filter by customer name (partial match)" }
      }
    }
  },
  {
    name: "tw_start_timer",
    description: "Start a live timer for a project. Stops any running timer first.",
    inputSchema: {
      type: "object",
      properties: {
        project: { type: "string", description: "Project name (partial match)" },
        description: { type: "string", description: "What are you working on?" }
      },
      required: ["project"]
    }
  },
  {
    name: "tw_stop_timer",
    description: "Stop the currently running timer and show duration + amount.",
    inputSchema: { type: "object", properties: {} }
  },
  {
    name: "tw_status",
    description: "Show current timer status and today's time entries with totals.",
    inputSchema: { type: "object", properties: {} }
  },
  {
    name: "tw_log_time",
    description: "Log a completed time entry (manual booking). Use for past work.",
    inputSchema: {
      type: "object",
      properties: {
        project: { type: "string", description: "Project name (partial match)" },
        hours: { type: "number", description: "Duration in hours (e.g. 1.5 for 1h30m)" },
        description: { type: "string", description: "What was done" },
        date: { type: "string", description: "Date YYYY-MM-DD (default: today)" },
        start_time: { type: "string", description: "Start HH:MM (default: 09:00)" },
        note: { type: "string", description: "Additional notes" }
      },
      required: ["project", "hours"]
    }
  },
  {
    name: "tw_summary",
    description: "Get time/revenue summary for a month grouped by customer and project.",
    inputSchema: {
      type: "object",
      properties: {
        month: { type: "integer", description: "Month 1-12 (default: current)" },
        year: { type: "integer", description: "Year (default: current)" },
        customer: { type: "string", description: "Filter by customer name" }
      }
    }
  },
  {
    name: "tw_entries",
    description: "List time entries for a date range, optionally filtered.",
    inputSchema: {
      type: "object",
      properties: {
        days: { type: "integer", description: "Number of past days (default: 7)" },
        customer: { type: "string", description: "Filter by customer name" },
        project: { type: "string", description: "Filter by project name" }
      }
    }
  }
];

const HANDLERS = {
  tw_list_customers: handleListCustomers,
  tw_list_projects: handleListProjects,
  tw_start_timer: handleStartTimer,
  tw_stop_timer: handleStopTimer,
  tw_status: handleStatus,
  tw_log_time: handleLogTime,
  tw_summary: handleSummary,
  tw_entries: handleEntries,
};

// ── MCP Server ───────────────────────────────────────────────────

const server = new Server({ name: "timeworm", version: "1.0.0" }, { capabilities: { tools: {} } });

server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools: TOOLS }));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args = {} } = request.params;
  const handler = HANDLERS[name];
  if (!handler) return { content: [{ type: "text", text: `Unknown tool: ${name}` }], isError: true };
  try {
    const text = handler(args);
    return { content: [{ type: "text", text }] };
  } catch (err) {
    return { content: [{ type: "text", text: `❌ Fehler: ${err.message}` }], isError: true };
  }
});

const transport = new StdioServerTransport();
await server.connect(transport);