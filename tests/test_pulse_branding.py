"""Prevent drift from the supplied Pulse Fitness brand rules.

No proprietary font binaries or private customer data are used in this test.
The reverse-logo geometry checks are fingerprinted from the supplied official
SVG asset (same three original path geometries, no logo redraw).
"""
from pathlib import Path
import json
import re
import zlib

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def test_corporate_logo_is_preserved_and_referenced():
    logo = (STATIC / "brand" / "pulse-fitness-reverse.svg").read_text()
    paths = re.findall(r'<path[^>]+d="([^"]+)"', logo)
    assert len(paths) == 3
    assert [(len(value), zlib.adler32(value.encode("utf-8")))
            for value in paths] == [
                (233, 0xF7832DDC),
                (861, 0x522AA206),
                (2870, 0xAB234A11),
            ]
    assert 'viewBox="0 0 324 70"' in logo
    assert "<script" not in logo.lower()
    index = (STATIC / "index.html").read_text()
    login = (STATIC / "pilot-login.html").read_text()
    for page in (index, login):
        assert "/static/brand/pulse-fitness-reverse.svg" in page
        assert 'alt="Pulse Fitness"' in page


def test_brand_palette_is_used_across_service_portal_and_quoting():
    styles = (STATIC / "pulse-brand.css").read_text()
    for brand_value in ("#19CDFF", "#1B1C1D", "#393E41",
                        "#6E7476", "#E0E0E0"):
        assert brand_value.lower() in styles.lower()
    assert ".pulse-invoice-drop" in styles
    assert ".pulse-smartquote-hero" in styles
    assert "prefers-reduced-motion" in styles
    assert "MaaxRounded" in styles
    assert "Proxima Nova" in styles
    index = (STATIC / "index.html").read_text()
    assert '/static/pulse-brand.css' in index
    assert 'pulse-brand-logo' in index
    assert 'Service &amp; Aftersales' in index
    assert "MEMBERSHIPS" not in index
    assert "COMMS CENTRE" not in index


def test_pwa_and_login_match_pulse_corporate_identity():
    manifest = json.loads((STATIC / "manifest.webmanifest").read_text())
    assert manifest["theme_color"].lower() == "#1b1c1d"
    assert "Pulse Fitness" in manifest["name"]
    login = (STATIC / "pilot-login.html").read_text()
    assert "SERVICE &amp; AFTERSALES" in login
    assert "pilot/login" in login
    assert "pulse-fitness-reverse.svg" in login


def test_smartquote_promotes_auto_matching_not_old_manual_checkbox():
    quote = (STATIC / "quoting-workspace.js").read_text()
    assert "pulse-smartquote-hero" in quote
    assert "pulse-step-strip" in quote
    assert 'class="pulse-invoice-drop"' in quote
    assert "Only unmatched" in quote
    assert "Exact Master machine-code matches are automatic" in quote
    assert "Equipment will not be added without your confirmation" not in quote
    print_layout = (STATIC / "quote-quick-draft.js").read_text()
    assert "/api/quoting/quick-draft/internal-preview.pdf" in print_layout
    server_pdf = (Path(__file__).resolve().parents[1] / "app" /
                  "quote_quick_pdf.py").read_text()
    assert "brand._page(" in server_pdf
    assert "NOT AUTHORISED FOR CUSTOMER ISSUE" in server_pdf
    assert "INTERNAL DRAFT" in print_layout


def test_proprietary_fonts_not_accidentally_published_to_public_source():
    assert not any(
        path.suffix.lower() in {".otf", ".ttf", ".woff", ".woff2"}
        for path in STATIC.rglob("*") if path.is_file()
    )


def test_customer_pdf_uses_official_vector_signature_and_brand_colours():
    import fitz
    from app import quote_customer_pdf as pdf

    assert pdf.NAVY == (27 / 255, 28 / 255, 29 / 255)
    assert pdf.ACCENT == (25 / 255, 205 / 255, 255 / 255)
    original = pdf._official_logo_pdf()
    assert original is not None
    with fitz.open(stream=original, filetype="pdf") as logo:
        assert logo.page_count == 1
        assert logo[0].rect.width == 324
        assert logo[0].rect.height == 70

    with fitz.open() as doc:
        pdf._page(doc, "PFQ-2026-000001", draft=True)
        assert doc.page_count == 1
        text = doc[0].get_text()
        assert "SERVICE & AFTERSALES" in text
        assert "PULSE FITNESS" in text
        assert "INTERNAL DRAFT ONLY" in text
        # The official vector logo is shown as a placed PDF object.
        assert doc[0].get_xobjects()
