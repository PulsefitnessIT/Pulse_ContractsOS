"""Reject malicious/compressed Excel uploads before customer-data parsing."""
from __future__ import annotations

import zipfile

import pytest

from app.data_readiness import workbook_check
from app.excel_io import ExcelSource, check_excel_archive_limits


def test_normal_small_zip_fits_safe_limits(tmp_path):
    target=tmp_path/"fictional_archive.xlsx"
    with zipfile.ZipFile(target,"w",zipfile.ZIP_DEFLATED) as file:
        file.writestr("xl/workbook.xml",'<workbook/>')
        file.writestr("xl/styles.xml",'<styleSheet/>')
    with zipfile.ZipFile(target) as z:
        assert check_excel_archive_limits(z) is None


def test_reject_archive_bomb_before_decompressing(tmp_path):
    target=tmp_path/"high_ratio.xlsx"
    # Several megabytes compressed to a very small file.
    with zipfile.ZipFile(target,"w",zipfile.ZIP_DEFLATED,compresslevel=9) as file:
        file.writestr("xl/workbook.xml","A" * (7 * 1024 * 1024))
        file.writestr("xl/styles.xml",'<styleSheet/>')
    with zipfile.ZipFile(target) as z:
        with pytest.raises(ValueError,match="compression ratio"):
            check_excel_archive_limits(z)
    result=workbook_check(target)
    assert result["valid"] is False
    assert result["issues"]


def test_reject_duplicate_path_ambiguity(tmp_path):
    target=tmp_path/"ambiguous.xlsx"
    with zipfile.ZipFile(target,"w") as z:
        z.writestr("xl/workbook.xml","fake")
        with pytest.warns(UserWarning,match="Duplicate name"):
            z.writestr("xl/workbook.xml","different")
    with zipfile.ZipFile(target) as archive:
        with pytest.raises(ValueError,match="duplicate archive paths"):
            check_excel_archive_limits(archive)
