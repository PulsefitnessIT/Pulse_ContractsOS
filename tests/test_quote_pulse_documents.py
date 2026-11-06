"""Fictional patterns matching three generations of Pulse PDF documents.

All customer names, invoice numbers and serials in these tests are invented.
The real customer PDFs are only validated locally, never committed to GitHub.
"""
from app.quote_pulse_documents import parse_pages


def test_legacy_invoice_keeps_zero_value_machines_and_wrapped_serials():
    content = """INVOICE
Description                                                   Qty      Unit        Discount       Total
290D5B          Fictional Indoor Rower                         6   £1,077.15                    £6,462.90
  Serial Numbers

    DE100-AAA-11111, DE100-AAA-22222, DE100-AAA-33333, DE100-AAA-
    44444, DE100-AAA-55555, DE100-AAA-66666

Product Group: H - Resistance Equipment
525H            Fictional Squat Machine                        1   £0.00                       £0.00
  Serial Numbers

    DS-8877

Product Group: Customer Care
Accessories    Accessories                                   1   £1,392.00                   £1,392.00
  Serial Numbers

    5206/3
"""
    parsed=parse_pages([{"page":1,"text":content}])
    assert parsed["format"]=="legacy"
    assert len(parsed["lines"])==3
    row=parsed["lines"][0]
    assert row["sku"]=="290D5B"
    assert row["quantity"]==6
    assert len(row["serial_numbers"])==6
    assert row["serial_numbers"][3]=="DE100-AAA-44444"
    assert parsed["lines"][1]["sku"]=="525H"
    assert parsed["lines"][1]["quantity"]==1
    assert parsed["lines"][2]["excluded_hint"] is True
    assert parsed["lines"][2]["serial_numbers"]==[]


def test_modern_invoice_links_leading_zeros_and_next_page_serials():
    first="""Invoice
Line Item Code        Description                  Quantity       Unit Price          Net
1    260G-ABU          Fictional Treadmill V4       4             £ 4,912.89          £ 19651.56
 Batch/Serial Number :     0000001
 Batch/Serial Number :     0000002
"""
    second="""Invoice
 Batch/Serial Number :     0000003
 Batch/Serial Number :     0000004
Line Item Code        Description                  Quantity       Unit Price          Net
2    264E-AAB          Fictional Curve Treadmill    2             £ 3,046.18          £ 6092.36
 Batch/Serial Number :     0000101
 Batch/Serial Number :     0000102
3    WAR-AAA-VAR       Extended Service Warranty    1             £ 0.00              £ 0.00
"""
    parsed=parse_pages([{"page":1,"text":first},{"page":2,"text":second}])
    assert parsed["format"]=="modern"
    assert len(parsed["lines"])==3
    assert parsed["lines"][0]["quantity"]==4
    assert parsed["lines"][0]["serial_numbers"]==[
        "0000001","0000002","0000003","0000004"
    ]
    assert parsed["lines"][0]["pages"]==[1,2]
    assert parsed["lines"][2]["excluded_hint"] is True


def test_delivery_note_received_not_sent_and_excludes_console_options():
    text="""DELIVERY NOTE
Products                                 Serial No             QTY SENT    QTY REC
260G-6.0-DRST      Fictional Running Machine        SN001, SN002         8            8
260G-Digital       Digital Freeview                 SN001, SN002         8            8
38-044             16kg Kettlebell                  TO FOLLOW            4            0
224B-AAB           Fictional Indoor Machine         EX111, EX112         4            4
                   EX113, EX114
"""
    parsed=parse_pages([{"page":1,"text":text}])
    assert parsed["document_type"]=="delivery_note"
    assert len(parsed["lines"])==4
    assert parsed["lines"][0]["quantity_received"]==8
    assert parsed["lines"][0]["serial_numbers"]==["SN001","SN002"]
    assert parsed["lines"][1]["excluded_hint"] is True
    assert parsed["lines"][2]["quantity_sent"]==4
    assert parsed["lines"][2]["quantity_received"]==0
    assert parsed["lines"][2]["serial_numbers"]==[]
    assert parsed["lines"][3]["serial_numbers"]==["EX111","EX112","EX113","EX114"]


def test_non_pulse_document_never_claims_machine_data():
    result=parse_pages([{"page":1,"text":"Statement of account\nNot a PDF sales document"}])
    assert result["document_type"]=="unrecognised"
    assert result["lines"]==[]
