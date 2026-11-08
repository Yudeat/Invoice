"""Tests for invoice business-rule validation."""

from datetime import timedelta
from decimal import Decimal

import pytest

from invoice_extractor.models import Invoice
from invoice_extractor.validation import validate


def codes(report):
    """Return the issue codes present in a validation report."""
    return {issue.code for issue in report.issues}


def test_correct_invoice_passes(good_invoice):
    report = validate(good_invoice)

    assert report.passed is True
    assert report.issues == []


def test_wrong_total_detected(good_invoice):
    good_invoice.total_amount = Decimal("113000")

    report = validate(good_invoice)

    assert report.passed is False
    assert "TOTAL_MISMATCH" in codes(report)


def test_wrong_line_total_detected(good_invoice):
    good_invoice.items[0].line_total = Decimal("60000")

    report = validate(good_invoice)

    assert report.passed is False
    assert "LINE_MISMATCH" in codes(report)
    assert "SUBTOTAL_MISMATCH" in codes(report)


def test_wrong_tax_detected(good_invoice):
    good_invoice.tax_amount = Decimal("10000")

    report = validate(good_invoice)

    assert report.passed is False
    assert "TAX_MISMATCH" in codes(report)


def test_due_date_before_invoice_date(good_invoice):
    assert good_invoice.invoice_date is not None
    good_invoice.due_date = (
        good_invoice.invoice_date - timedelta(days=1)
    )

    report = validate(good_invoice)

    assert report.passed is False
    assert "DATE_ORDER" in codes(report)


def test_due_date_equal_to_invoice_date_is_allowed(good_invoice):
    assert good_invoice.invoice_date is not None
    good_invoice.due_date = good_invoice.invoice_date

    report = validate(good_invoice)

    assert report.passed is True
    assert "DATE_ORDER" not in codes(report)


def test_missing_fields_reported_without_crashing():
    report = validate(Invoice())

    assert report.passed is False
    assert {
        "MISSING_INVOICE_NUMBER",
        "MISSING_INVOICE_DATE",
        "MISSING_SUPPLIER_NAME",
        "MISSING_TOTAL_AMOUNT",
        "NO_ITEMS",
    } <= codes(report)

    assert "MISSING_CURRENCY" in codes(report)
    assert "TOTAL_MISMATCH" not in codes(report)


@pytest.mark.parametrize("value", ["", "   "])
def test_blank_required_string_is_missing(good_invoice, value):
    good_invoice.invoice_number = value

    report = validate(good_invoice)

    assert report.passed is False
    assert "MISSING_INVOICE_NUMBER" in codes(report)


def test_total_checked_against_items_when_no_subtotal(good_invoice):
    good_invoice.subtotal = None
    good_invoice.tax_rate_percent = None

    # Keep the known tax amount so the total can be verified.
    good_invoice.total_amount = Decimal("999")

    report = validate(good_invoice)

    assert report.passed is False
    assert "TOTAL_MISMATCH" in codes(report)
    assert "TOTAL_UNVERIFIED" not in codes(report)


def test_correct_total_passes_when_subtotal_is_missing(good_invoice):
    good_invoice.subtotal = None

    report = validate(good_invoice)

    assert report.passed is True
    assert report.issues == []


def test_missing_tax_does_not_assume_zero(good_invoice):
    good_invoice.tax_amount = None
    good_invoice.total_amount = Decimal("999")

    report = validate(good_invoice)

    assert report.passed is True
    assert "TOTAL_UNVERIFIED" in codes(report)
    assert "TOTAL_MISMATCH" not in codes(report)
    assert "TAX_MISMATCH" not in codes(report)


def test_explicit_zero_tax_allows_total_verification(good_invoice):
    assert good_invoice.subtotal is not None

    good_invoice.tax_rate_percent = Decimal("0")
    good_invoice.tax_amount = Decimal("0")
    good_invoice.total_amount = good_invoice.subtotal

    report = validate(good_invoice)

    assert report.passed is True
    assert report.issues == []


@pytest.mark.parametrize(
    ("difference", "expected_passed"),
    [
        (Decimal("0"), True),
        (Decimal("0.005"), True),
        (Decimal("0.01"), True),
        (Decimal("-0.01"), True),
        (Decimal("0.011"), False),
        (Decimal("-0.011"), False),
    ],
)
def test_total_rounding_tolerance(
    good_invoice,
    difference,
    expected_passed,
):
    assert good_invoice.total_amount is not None
    good_invoice.total_amount += difference

    report = validate(good_invoice)

    assert report.passed is expected_passed
    assert (
        "TOTAL_MISMATCH" in codes(report)
    ) is (not expected_passed)


def test_incomplete_item_is_warning_only(good_invoice):
    good_invoice.items[1].unit_price = None

    report = validate(good_invoice)

    assert report.passed is True
    assert "ITEM_INCOMPLETE" in codes(report)
    assert "LINE_MISMATCH" not in codes(report)


def test_missing_line_total_does_not_use_partial_sum(good_invoice):
    good_invoice.items[0].line_total = None

    report = validate(good_invoice)

    assert report.passed is True
    assert "ITEM_NO_TOTAL" in codes(report)
    assert "SUBTOTAL_MISMATCH" not in codes(report)

    # The printed subtotal still allows total verification.
    assert "TOTAL_UNVERIFIED" not in codes(report)


def test_partial_line_totals_cannot_replace_missing_subtotal(
    good_invoice,
):
    good_invoice.subtotal = None
    good_invoice.items[0].line_total = None

    report = validate(good_invoice)

    assert report.passed is True
    assert "ITEM_NO_TOTAL" in codes(report)
    assert "TOTAL_UNVERIFIED" in codes(report)
    assert "SUBTOTAL_MISMATCH" not in codes(report)
    assert "TAX_MISMATCH" not in codes(report)
    assert "TOTAL_MISMATCH" not in codes(report)


def test_missing_operands_do_not_hide_missing_line_total(good_invoice):
    item = good_invoice.items[0]
    item.quantity = None
    item.unit_price = None
    item.line_total = None

    report = validate(good_invoice)

    assert report.passed is True
    assert "ITEM_INCOMPLETE" in codes(report)
    assert "ITEM_NO_TOTAL" in codes(report)
    assert "LINE_MISMATCH" not in codes(report)


def test_missing_description_is_warning_only(good_invoice):
    good_invoice.items[0].description = None

    report = validate(good_invoice)

    assert report.passed is True
    assert "ITEM_NO_DESCRIPTION" in codes(report)


def test_missing_currency_is_warning_only(good_invoice):
    good_invoice.currency = None

    report = validate(good_invoice)

    assert report.passed is True
    assert "MISSING_CURRENCY" in codes(report)


def test_due_date_without_invoice_date_reports_partial_date(
    good_invoice,
):
    assert good_invoice.invoice_date is not None
    good_invoice.due_date = good_invoice.invoice_date
    good_invoice.invoice_date = None

    report = validate(good_invoice)

    assert report.passed is False
    assert "MISSING_INVOICE_DATE" in codes(report)
    assert "DATE_PARTIAL" in codes(report)
    assert "DATE_ORDER" not in codes(report)


def test_validate_does_not_modify_invoice(good_invoice):
    before = good_invoice.model_dump(mode="python")

    validate(good_invoice)

    assert good_invoice.model_dump(mode="python") == before