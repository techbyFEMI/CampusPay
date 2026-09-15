import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls
import os

def set_cell_background(cell, fill_color):
    tcPr = cell._element.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_color}"/>')
    tcPr.append(shd)

def create_document():
    doc = docx.Document()

    # Set Margins
    for section in doc.sections:
        section.top_margin = Inches(1)
        section.bottom_margin = Inches(1)
        section.left_margin = Inches(1)
        section.right_margin = Inches(1)

    # Styles setup
    styles = doc.styles
    normal_style = styles['Normal']
    normal_style.font.name = 'Calibri'
    normal_style.font.size = Pt(11)
    normal_style.font.color.rgb = RGBColor(0x2D, 0x37, 0x48)

    # Title
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_title = p_title.add_run("CampusPay — Department Pilot (Course-Rep Model)")
    run_title.font.name = 'Calibri'
    run_title.font.size = Pt(24)
    run_title.font.bold = True
    run_title.font.color.rgb = RGBColor(0x1A, 0x36, 0x5D)

    # Subtitle
    p_sub = doc.add_paragraph()
    p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_sub = p_sub.add_run("Technical Specification & Implementation Guide (Immediate Payout Flow)")
    run_sub.font.name = 'Calibri'
    run_sub.font.size = Pt(14)
    run_sub.font.italic = True
    run_sub.font.color.rgb = RGBColor(0x4A, 0x55, 0x68)

    doc.add_paragraph() # Spacer

    def add_h1(text):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(18)
        p.paragraph_format.space_after = Pt(6)
        run = p.add_run(text)
        run.font.name = 'Calibri'
        run.font.size = Pt(18)
        run.font.bold = True
        run.font.color.rgb = RGBColor(0x1A, 0x36, 0x5D)
        return p

    def add_h2(text):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(14)
        p.paragraph_format.space_after = Pt(4)
        run = p.add_run(text)
        run.font.name = 'Calibri'
        run.font.size = Pt(14)
        run.font.bold = True
        run.font.color.rgb = RGBColor(0x2B, 0x6C, 0xB0)
        return p

    def add_callout(text, title="NOTE"):
        tbl = doc.add_table(rows=1, cols=1)
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        cell = tbl.cell(0, 0)
        set_cell_background(cell, "EDF2F7")
        p = cell.paragraphs[0]
        p.paragraph_format.space_before = Pt(4)
        p.paragraph_format.space_after = Pt(4)
        run_t = p.add_run(f"[{title}] ")
        run_t.font.bold = True
        run_t.font.color.rgb = RGBColor(0x2B, 0x6C, 0xB0)
        run_b = p.add_run(text)
        doc.add_paragraph()

    # 1. Executive Summary & Architecture Overview
    add_h1("1. Executive Summary & Core Purpose")
    doc.add_paragraph(
        "The CampusPay Department Pilot transitions the platform to a Course-Rep Model. "
        "Every individual student payment is credited immediately to the Course Rep's wallet/account upon checkout. "
        "Products remain available for payment as long as the Rep leaves the 'is_available' toggle active. "
        "When items are handed out physically, the Rep scans the student's QR code purely to record attendance/collection."
    )

    add_h2("1.1 Architecture & Flow Comparison")
    
    table = doc.add_table(rows=5, cols=3)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False

    headers = ["Feature Layer", "Original CampusPay", "Department Pilot (Course-Rep)"]
    hdr_cells = table.rows[0].cells
    for i, title in enumerate(headers):
        hdr_cells[i].text = title
        set_cell_background(hdr_cells[i], "2B6CB0")
        for p in hdr_cells[i].paragraphs:
            for run in p.runs:
                run.font.bold = True
                run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    data = [
        ("Seller Model", "Multi-vendor marketplace", "Single Rep per department"),
        ("Payout Timing", "Held in escrow until physical QR scan", "Immediate release to Rep wallet upon student checkout"),
        ("Product Availability", "Static catalog", "Rep toggles 'is_available' (ON/OFF) anytime"),
        ("QR Scan Function", "Triggers bank transfer", "Fulfillment & attendance tracking only (no money movement)")
    ]

    for row_idx, row_data in enumerate(data, start=1):
        row_cells = table.rows[row_idx].cells
        bg_color = "F7FAFC" if row_idx % 2 == 1 else "FFFFFF"
        for col_idx, text in enumerate(row_data):
            row_cells[col_idx].text = text
            set_cell_background(row_cells[col_idx], bg_color)

    doc.add_paragraph()

    # 2. Key Workflow
    add_h1("2. Student & Rep Workflow")
    doc.add_paragraph("1. Rep Posts Item: Rep creates an item (e.g. 'Class Dues', 'Computer Science Handout') with price.")
    doc.add_paragraph("2. Student Checkout: Student pays from wallet balance. Funds credit IMMEDIATELY to Rep wallet.")
    doc.add_paragraph("3. Availability Toggle: Rep turns off 'is_available' when sales stop or quota is reached.")
    doc.add_paragraph("4. Distribution Scan: Rep scans student QR token at collection to mark 'is_collected=True'.")

    # 3. Database Schema
    add_h1("3. Database Schema Specification")
    doc.add_paragraph("• product: product_id (PK), vendor_id (FK -> Rep), name, description, price, is_available (Boolean toggle)")
    doc.add_paragraph("• order: order_id (PK), student_id (FK), vendor_id (FK -> Rep), item_amount, order_status, is_collected (Boolean), collected_at (DateTime)")

    # Save
    doc_path = "/home/femi-dev/CampusPay/CampusPay_Department_Pilot_Technical_Spec.docx"
    doc.save(doc_path)
    print(f"Updated docx saved to {doc_path}")

create_document()
