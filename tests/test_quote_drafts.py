"""Synthetic safety checks for draft-only unified quotations."""
import pytest
from fastapi import HTTPException
from app import quote_drafts

def test_draft_never_generates_a_price():
    result = quote_drafts.validate_draft({
        "customer":"Example Ltd","site":"Demo Site","tier":"Silver",
        "equipment":[{"description":"Treadmill", "quantity":2,"item_code":"TEST001"}]})
    assert result["price"] is None
    assert result["approved"] is False
    assert result["commercial_status"] == "Unpriced draft"
    assert result["equipment"][0]["quantity"] == 2

@pytest.mark.parametrize("qty",[0,-1,1.5,True,"2"])
def test_invalid_quantity_rejected(qty):
    with pytest.raises(HTTPException) as error:
        quote_drafts.validate_draft({"customer":"Demo","site":"Gym",
           "equipment":[{"description":"Treadmill","quantity":qty}]})
    assert error.value.status_code == 422

def test_unknown_maintenance_package_rejected():
    with pytest.raises(HTTPException):
        quote_drafts.validate_draft({"customer":"Demo","site":"Gym","tier":"Unsupported"})

def test_empty_customer_rejected():
    with pytest.raises(HTTPException):
        quote_drafts.validate_draft({"customer":"","site":"Gym"})

def test_too_many_lines_rejected():
    with pytest.raises(HTTPException):
        quote_drafts.validate_draft({"customer":"Demo","site":"Gym",
           "equipment":[{"description":"Test"} for _ in range(501)]})
