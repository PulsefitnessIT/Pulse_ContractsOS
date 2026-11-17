"""Contract agreement + exact supplied-format Sicon template previews, synthetic only."""
import datetime as dt
import io
import unittest
import xml.etree.ElementTree as ET
import zipfile
from unittest.mock import patch
from app import handover_documents as doc
from app.quote_intake import validate
from test_pilot_data_contract_setup import sample

NS="{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def fake_template(kind):
    if kind=="contract":
        names=["Contract Number"]+[f"Filler Column {n}" for n in range(2,239)]+["CL AnalysisCode 150"]
    else:
        names=["Sicon Customer Ref", "Location Description", "Sublocation Description",
          "Supplier Reference", "Supplier Name", "Contract Number", "Contract Line No",
          "SLA Name", "Stock Item Code", "Description", "Make", "Model",
          "Serial Number", "Install Date", "Manufacturer Warranty Expiry Date",
          "Last Service Date", "Service Interval", "Service Period", "Next Service Date",
          "ID Number", "Service Template", "Equipment Group", "service_provider",
          "unit_price", "replacement_cost", "length", "width", "height", "MOD-Force"]+[""]*15
    root=ET.Element(NS+"worksheet")
    data=ET.SubElement(root,NS+"sheetData")
    for n,values in enumerate([names,["SAMPLE MUST BE DELETED"]+[""]*(len(names)-1)],1):
        row=ET.SubElement(data,NS+"row",{"r":str(n)})
        for i,v in enumerate(values,1):
            c=ET.SubElement(row,NS+"c",{"r":doc._column(i),"t":"inlineStr"})
            ET.SubElement(ET.SubElement(c,NS+"is"),NS+"t").text=v
    x=io.BytesIO()
    with zipfile.ZipFile(x,"w") as z:
        z.writestr("xl/worksheets/sheet1.xml",ET.tostring(root))
        z.writestr("xl/workbook.xml","<sample/>")
    return x.getvalue(),names


def fill_approved_fixture(template,kind,rows):
    # Synthetic fixtures are not the private Sicon source templates; explicitly
    # pin only their test-only header checksum for the duration of this call.
    with zipfile.ZipFile(io.BytesIO(template)) as z:
        root=ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
        names=doc._headers(root.find(NS+"sheetData")[0])
    import hashlib
    digest=hashlib.sha256("\0".join(names).encode("utf-8")).hexdigest()
    with patch.dict(doc.APPROVED_HEADER_SHA256,{kind:digest}):
        return doc.workbook_from_template(template,kind,rows)


def data():
    q=validate(sample())
    q["contract"]["reference"]="CON-TEST-001"
    # Fixture stage 2026 from other tests. Ensure both stages on or before 2027.
    q["equipment"][0]["cover_start"]="2026-01-01"
    q["contract"]["start_date"]="2026-01-01"
    return q


def verified():
    return {"sage_account_ref":"SAGE-TEST-001",
            "contract_reference":"CON-TEST-001",
            "warehouse_name":"TEST-WAREHOUSE",
            "billing_stock_code":"TEST-CON-MAINTENANCE",
            "sicon_delivery_address":"SITE-DELIVERY-001",
            "sicon_customer_ref":"SICON-TEST-ACCOUNT",
            "sicon_location_description":"Example community gym",
            "sla_name":"GOLD-TEST-SLA",
            "equipment_make":"Demo Manufacturer",
            "billing_frequency":"Monthly"}


class ExcelTemplatePreservation(unittest.TestCase):
    def test_contract_239_headers_and_remove_supplier_example_rows(self):
        source,names=fake_template("contract")
        row=doc.contract_rows(data(),verified())[0]
        allowed={key:row[key] for key in row if key in names}
        generated=fill_approved_fixture(source,"contract",[allowed,allowed])
        with zipfile.ZipFile(io.BytesIO(generated)) as z:
            root=ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
            rows=root.find(NS+"sheetData").findall(NS+"row")
            self.assertEqual(doc._headers(rows[0]),names)
            self.assertEqual(len(rows),3)
            self.assertNotIn(b"SAMPLE MUST BE DELETED",z.read("xl/worksheets/sheet1.xml"))
            self.assertIn(b"CON-TEST-001",z.read("xl/worksheets/sheet1.xml"))
    def test_equipment_29_headers_and_one_record_per_serial(self):
        q=data()
        # Change second group to due for this focused unit test.
        with patch.object(doc,"today",return_value=dt.date(2028,1,1)):
            rows=doc.equipment_rows(q,verified(),"SICON-TEST-CON","2027-07-01",
                                    {"demo-B":["TEST-002","TEST-003"]})
        self.assertEqual(len(rows),2)
        self.assertEqual([r["Serial Number"] for r in rows],["TEST-002","TEST-003"])
        self.assertEqual(rows[0]["Contract Line No"],2)
        tmpl,names=fake_template("equipment")
        b=fill_approved_fixture(tmpl,"equipment",rows)
        with zipfile.ZipFile(io.BytesIO(b)) as z:
            root=ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
            rec=root.find(NS+"sheetData").findall(NS+"row")
            self.assertEqual(doc._headers(rec[0]),names)
            self.assertEqual(len(rec),3)
    def test_change_of_supplier_template_is_blocked(self):
        src,names=fake_template("equipment")
        with self.assertRaisesRegex(doc.TemplateError,"headers"):
            doc.workbook_from_template(src,"contract",[])
    def test_no_early_equipment_or_unverified_make(self):
        with self.assertRaisesRegex(doc.TemplateError,"future-dated"):
            doc.equipment_rows(data(),verified(),"SICON","2027-07-01")
        v=verified()
        v["equipment_make"]=""
        with self.assertRaisesRegex(doc.TemplateError,"manufacturer"):
            doc.equipment_rows(data(),v,"SICON","2026-01-01")
    def test_stages_billing_rows_have_matching_common_expiry(self):
        q=data()
        rows=doc.contract_rows(q,verified())
        self.assertEqual(len(rows),2)
        self.assertEqual([r["Contract Line Number"] for r in rows],[1,2])
        self.assertEqual([r["Contract End Date"] for r in rows],["31/12/2027","31/12/2027"])
        self.assertEqual([r["Contract Start Date"] for r in rows],["01/01/2026","01/07/2027"])
        self.assertEqual([r["Bill Cover From Date"] for r in rows],["01/01/2026","01/07/2027"])
    def test_mandatory_sicon_identifiers_not_inferred(self):
        v=verified()
        del v["billing_stock_code"]
        with self.assertRaisesRegex(doc.TemplateError,"billing stock code"):
            doc.contract_rows(data(),v)


class AgreementPdf(unittest.TestCase):
    def test_approved_terms_unmodified_in_preview(self):
        try:import fitz
        except ImportError:self.skipTest("pymupdf is not installed")
        source=fitz.open()
        for i in range(8):
            p=source.new_page(width=540,height=780)
            label=("Schedule 6 - Exceptions" if i==6
                   else "MAINTENANCE AGREEMENT legal clauses unchanged" if i==7
                   else "Maintenance Agreement")
            p.insert_text((72,70),label,fontsize=12)
        orig_legal=source[7].get_text()
        b=source.tobytes()
        q=data()
        preview=doc.agreement_preview(b,q,verified(),{"demo-B":["TEST-002","TEST-003"]})
        rendered=fitz.open(stream=preview,filetype="pdf")
        self.assertEqual(len(rendered),7)
        self.assertIn("Fictional Council",rendered[2].get_text())
        self.assertIn("100H-AAA",rendered[2].get_text())
        self.assertIn("200G-ABC",rendered[2].get_text())
        self.assertIn("DRAFT FOR CONTRACT REVIEW",rendered[0].get_text())
        self.assertIn("MAINTENANCE AGREEMENT legal clauses unchanged",rendered[6].get_text())
        self.assertIn(orig_legal.strip(),rendered[6].get_text())
        rendered.close();source.close()
