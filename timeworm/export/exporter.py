import csv
import io
from datetime import datetime
from pathlib import Path
from typing import Optional

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
)

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


def export_pdf(filepath: str, start_date: str, end_date: str,
               project_id: Optional[int] = None):
    """Export time entries as a PDF invoice / Stundennachweis."""
    entries, summary = _get_report_data(start_date, end_date, project_id)

    doc = SimpleDocTemplate(
        filepath, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=20 * mm, bottomMargin=20 * mm
    )
    styles = getSampleStyleSheet()
    elements = []

    # Title
    title_style = ParagraphStyle(
        'InvoiceTitle', parent=styles['Title'],
        fontSize=18, spaceAfter=6 * mm
    )
    elements.append(Paragraph("Stundennachweis", title_style))

    # Period
    start_dt = datetime.fromisoformat(start_date)
    end_dt = datetime.fromisoformat(end_date)
    period = (
        f"Zeitraum: {start_dt.strftime('%d.%m.%Y')} – "
        f"{end_dt.strftime('%d.%m.%Y')}"
    )
    elements.append(Paragraph(period, styles['Normal']))
    elements.append(Spacer(1, 8 * mm))

    # --- Summary table ---
    if summary:
        elements.append(Paragraph("Zusammenfassung", styles['Heading2']))
        sum_data = [['Projekt', 'Stunden', '€/h', 'Betrag (€)']]
        total_hours = 0.0
        total_amount = 0.0
        for s in summary:
            hours = s['total_hours'] or 0
            amount = hours * s['hourly_rate']
            total_hours += hours
            total_amount += amount
            sum_data.append([
                s['name'],
                f"{hours:.2f}",
                f"{s['hourly_rate']:.2f}",
                f"{amount:.2f}"
            ])
        sum_data.append(['Gesamt', f"{total_hours:.2f}", '', f"{total_amount:.2f}"])

        col_widths = [60 * mm, 30 * mm, 25 * mm, 35 * mm]
        sum_table = Table(sum_data, colWidths=col_widths)
        sum_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2E3436')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#F5F5F5')]),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        elements.append(sum_table)
        elements.append(Spacer(1, 8 * mm))

    # --- Detail table ---
    if entries:
        elements.append(Paragraph("Einzelnachweise", styles['Heading2']))
        detail_data = [['Projekt', 'Datum', 'Von', 'Bis', 'Stunden', 'Betrag (€)', 'Notiz']]
        for e in entries:
            start = datetime.fromisoformat(e['start_time'])
            end = datetime.fromisoformat(e['end_time'])
            hours = (end - start).total_seconds() / 3600
            amount = hours * e['hourly_rate']
            detail_data.append([
                e['project_name'],
                start.strftime('%d.%m.%Y'),
                start.strftime('%H:%M'),
                end.strftime('%H:%M'),
                f"{hours:.2f}",
                f"{amount:.2f}",
                e['note'] or ''
            ])

        col_widths = [35 * mm, 22 * mm, 15 * mm, 15 * mm, 18 * mm, 22 * mm, 40 * mm]
        detail_table = Table(detail_data, colWidths=col_widths, repeatRows=1)
        detail_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2E3436')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (2, 0), (5, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F5F5')]),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))
        elements.append(detail_table)

    doc.build(elements)
