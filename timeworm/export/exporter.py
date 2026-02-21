import csv
import io
from datetime import datetime
from pathlib import Path
from typing import Optional

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

from ..repository import TimeEntryRepository


def _get_report_data(start_date: str, end_date: str, project_id: Optional[int] = None):
    entries = TimeEntryRepository.get_entries(project_id, start_date, end_date)
    summary = TimeEntryRepository.get_summary(start_date, end_date)
    return entries, summary


def export_csv(filepath: str, start_date: str, end_date: str,
               project_id: Optional[int] = None):
    """Export time entries as CSV."""
    entries, _ = _get_report_data(start_date, end_date, project_id)
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow(['Projekt', 'Start', 'Ende', 'Stunden', '€/h', 'Betrag', 'Notiz'])
        for e in entries:
            start = datetime.fromisoformat(e['start_time'])
            end = datetime.fromisoformat(e['end_time'])
            hours = (end - start).total_seconds() / 3600
            amount = hours * e['hourly_rate']
            writer.writerow([
                e['project_name'],
                start.strftime('%d.%m.%Y %H:%M'),
                end.strftime('%d.%m.%Y %H:%M'),
                f"{hours:.2f}",
                f"{e['hourly_rate']:.2f}",
                f"{amount:.2f}",
                e['note']
            ])


def export_excel(filepath: str, start_date: str, end_date: str,
                 project_id: Optional[int] = None):
    """Export time entries and summary as Excel."""
    entries, summary = _get_report_data(start_date, end_date, project_id)

    wb = Workbook()

    # --- Detail sheet ---
    ws = wb.active
    ws.title = "Zeiteinträge"
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="2E3436", end_color="2E3436", fill_type="solid")
    headers = ['Projekt', 'Datum', 'Start', 'Ende', 'Stunden', '€/h', 'Betrag (€)', 'Notiz']
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center')

    for row, e in enumerate(entries, 2):
        start = datetime.fromisoformat(e['start_time'])
        end = datetime.fromisoformat(e['end_time'])
        hours = (end - start).total_seconds() / 3600
        amount = hours * e['hourly_rate']
        ws.cell(row=row, column=1, value=e['project_name'])
        ws.cell(row=row, column=2, value=start.strftime('%d.%m.%Y'))
        ws.cell(row=row, column=3, value=start.strftime('%H:%M'))
        ws.cell(row=row, column=4, value=end.strftime('%H:%M'))
        ws.cell(row=row, column=5, value=round(hours, 2))
        ws.cell(row=row, column=6, value=e['hourly_rate'])
        ws.cell(row=row, column=7, value=round(amount, 2))
        ws.cell(row=row, column=8, value=e['note'])

    for col in ws.columns:
        ws.column_dimensions[col[0].column_letter].width = 16

    # --- Summary sheet ---
    ws2 = wb.create_sheet("Zusammenfassung")
    for col, h in enumerate(['Projekt', 'Stunden', '€/h', 'Betrag (€)', 'Einträge'], 1):
        cell = ws2.cell(row=1, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill

    total_hours = 0
    total_amount = 0
    for row, s in enumerate(summary, 2):
        hours = s['total_hours'] or 0
        amount = hours * s['hourly_rate']
        total_hours += hours
        total_amount += amount
        ws2.cell(row=row, column=1, value=s['name'])
        ws2.cell(row=row, column=2, value=round(hours, 2))
        ws2.cell(row=row, column=3, value=s['hourly_rate'])
        ws2.cell(row=row, column=4, value=round(amount, 2))
        ws2.cell(row=row, column=5, value=s['entry_count'])

    # Totals row
    total_row = len(summary) + 2
    ws2.cell(row=total_row, column=1, value="GESAMT").font = Font(bold=True)
    ws2.cell(row=total_row, column=2, value=round(total_hours, 2)).font = Font(bold=True)
    ws2.cell(row=total_row, column=4, value=round(total_amount, 2)).font = Font(bold=True)

    for col in ws2.columns:
        ws2.column_dimensions[col[0].column_letter].width = 16

    wb.save(filepath)
