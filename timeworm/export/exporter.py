import csv
from datetime import datetime
from typing import Optional

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
)

from ..repository import TimeEntryRepository


def _get_report_data(start_date: str, end_date: str, project_id: Optional[int] = None):
    entries = TimeEntryRepository.get_entries(
        project_id=project_id, start_date=start_date, end_date=end_date
    )
    summary = TimeEntryRepository.get_summary(start_date, end_date)
    customer_summary = TimeEntryRepository.get_summary_by_customer(start_date, end_date)
    return entries, summary, customer_summary


def export_csv(filepath: str, start_date: str, end_date: str,
               project_id: Optional[int] = None):
    """Export time entries as semicolon-delimited CSV."""
    entries, _, _ = _get_report_data(start_date, end_date, project_id)
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow(['Kunde', 'Projekt', 'Datum', 'Start', 'Ende',
                         'Stunden', '€/h', 'Betrag', 'Notiz', 'Beschreibung'])
        for e in entries:
            start = datetime.fromisoformat(e['start_time'])
            end = datetime.fromisoformat(e['end_time'])
            hours = (end - start).total_seconds() / 3600
            amount = hours * e['hourly_rate']
            writer.writerow([
                e['customer_name'],
                e['project_name'],
                start.strftime('%d.%m.%Y'),
                start.strftime('%H:%M'),
                end.strftime('%H:%M'),
                f"{hours:.2f}",
                f"{e['hourly_rate']:.2f}",
                f"{amount:.2f}",
                e.get('note', ''),
                e.get('description', ''),
            ])


def export_excel(filepath: str, start_date: str, end_date: str,
                 project_id: Optional[int] = None):
    """Export time entries and summary as Excel workbook."""
    entries, summary, customer_summary = _get_report_data(start_date, end_date, project_id)

    wb = Workbook()
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="2E3436", end_color="2E3436", fill_type="solid")

    # --- Detail sheet ---
    ws = wb.active
    ws.title = "Zeiteinträge"
    headers = ['Kunde', 'Projekt', 'Datum', 'Start', 'Ende',
               'Stunden', '€/h', 'Betrag (€)', 'Notiz', 'Beschreibung']
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
        ws.cell(row=row, column=1, value=e['customer_name'])
        ws.cell(row=row, column=2, value=e['project_name'])
        ws.cell(row=row, column=3, value=start.strftime('%d.%m.%Y'))
        ws.cell(row=row, column=4, value=start.strftime('%H:%M'))
        ws.cell(row=row, column=5, value=end.strftime('%H:%M'))
        ws.cell(row=row, column=6, value=round(hours, 2))
        ws.cell(row=row, column=7, value=e['hourly_rate'])
        ws.cell(row=row, column=8, value=round(amount, 2))
        ws.cell(row=row, column=9, value=e.get('note', ''))
        ws.cell(row=row, column=10, value=e.get('description', ''))

    for col in ws.columns:
        ws.column_dimensions[col[0].column_letter].width = 16

    # --- Summary sheet ---
    ws2 = wb.create_sheet("Zusammenfassung")
    sum_headers = ['Kunde', 'Projekt', 'Stunden', '€/h', 'Betrag (€)', 'Einträge']
    for col, h in enumerate(sum_headers, 1):
        cell = ws2.cell(row=1, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill

    total_hours = 0
    total_amount = 0
    row_num = 2

    # Group by customer
    projects_by_customer = {}
    for s in summary:
        projects_by_customer.setdefault(s['customer_name'], []).append(s)

    for cust in customer_summary:
        cname = cust['customer_name']
        chours = cust['total_hours'] or 0
        camount = cust['total_amount'] or 0
        total_hours += chours
        total_amount += camount

        # Customer row (bold)
        ws2.cell(row=row_num, column=1, value=cname).font = Font(bold=True)
        ws2.cell(row=row_num, column=3, value=round(chours, 2)).font = Font(bold=True)
        ws2.cell(row=row_num, column=5, value=round(camount, 2)).font = Font(bold=True)
        row_num += 1

        for proj in projects_by_customer.get(cname, []):
            phours = proj['total_hours'] or 0
            pamount = phours * proj['hourly_rate']
            ws2.cell(row=row_num, column=2, value=proj['project_name'])
            ws2.cell(row=row_num, column=3, value=round(phours, 2))
            ws2.cell(row=row_num, column=4, value=proj['hourly_rate'])
            ws2.cell(row=row_num, column=5, value=round(pamount, 2))
            ws2.cell(row=row_num, column=6, value=proj['entry_count'])
            row_num += 1

    # Totals
    ws2.cell(row=row_num, column=1, value="GESAMT").font = Font(bold=True, size=12)
    ws2.cell(row=row_num, column=3, value=round(total_hours, 2)).font = Font(bold=True, size=12)
    ws2.cell(row=row_num, column=5, value=round(total_amount, 2)).font = Font(bold=True, size=12)

    for col in ws2.columns:
        ws2.column_dimensions[col[0].column_letter].width = 18

    wb.save(filepath)


def export_pdf(filepath: str, start_date: str, end_date: str,
               project_id: Optional[int] = None):
    """Export as PDF Stundennachweis."""
    entries, summary, customer_summary = _get_report_data(start_date, end_date, project_id)

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
        f"Zeitraum: {start_dt.strftime('%d.%m.%Y')} \u2013 "
        f"{end_dt.strftime('%d.%m.%Y')}"
    )
    elements.append(Paragraph(period, styles['Normal']))
    elements.append(Spacer(1, 8 * mm))

    # --- Summary by customer ---
    if customer_summary:
        elements.append(Paragraph("Zusammenfassung nach Kunde", styles['Heading2']))
        sum_data = [['Kunde / Projekt', 'Stunden', '\u20ac/h', 'Betrag (\u20ac)']]
        total_hours = 0.0
        total_amount = 0.0

        projects_by_customer = {}
        for s in summary:
            projects_by_customer.setdefault(s['customer_name'], []).append(s)

        for cust in customer_summary:
            cname = cust['customer_name']
            chours = cust['total_hours'] or 0
            camount = cust['total_amount'] or 0
            total_hours += chours
            total_amount += camount
            sum_data.append([cname, f"{chours:.2f}", '', f"{camount:.2f}"])

            for proj in projects_by_customer.get(cname, []):
                phours = proj['total_hours'] or 0
                pamount = phours * proj['hourly_rate']
                sum_data.append([
                    f"    {proj['project_name']}",
                    f"{phours:.2f}",
                    f"{proj['hourly_rate']:.2f}",
                    f"{pamount:.2f}"
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
            ('ROWBACKGROUNDS', (0, 1), (-1, -2),
             [colors.white, colors.HexColor('#F5F5F5')]),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        elements.append(sum_table)
        elements.append(Spacer(1, 8 * mm))

    # --- Detail table ---
    if entries:
        elements.append(Paragraph("Einzelnachweise", styles['Heading2']))
        detail_data = [['Kunde', 'Projekt', 'Datum', 'Von', 'Bis',
                        'Stunden', 'Betrag (\u20ac)', 'Notiz']]
        for e in entries:
            start = datetime.fromisoformat(e['start_time'])
            end = datetime.fromisoformat(e['end_time'])
            hours = (end - start).total_seconds() / 3600
            amount = hours * e['hourly_rate']
            detail_data.append([
                e['customer_name'],
                e['project_name'],
                start.strftime('%d.%m.%Y'),
                start.strftime('%H:%M'),
                end.strftime('%H:%M'),
                f"{hours:.2f}",
                f"{amount:.2f}",
                e.get('note', '') or ''
            ])

        col_widths = [28 * mm, 28 * mm, 20 * mm, 14 * mm, 14 * mm,
                      16 * mm, 20 * mm, 30 * mm]
        detail_table = Table(detail_data, colWidths=col_widths, repeatRows=1)
        detail_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2E3436')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 7),
            ('ALIGN', (3, 0), (6, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1),
             [colors.white, colors.HexColor('#F5F5F5')]),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))
        elements.append(detail_table)

    doc.build(elements)
