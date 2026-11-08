"""AI extraction schemas, domain models, and normalization helpers."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


_ISO_DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


# ---------------------------------------------------------------------------
# AI boundary schemas
# ---------------------------------------------------------------------------


class RawLineItem(BaseModel):
    """A line item returned by the extraction service."""

    model_config = ConfigDict(allow_inf_nan=False)

    description: str | None = Field(
        default=None,
        description="Item description as printed",
    )
    quantity: float | None = Field(
        default=None,
        description="Numeric quantity only, e.g. 50",
    )
    unit: str | None = Field(
        default=None,
        description="Unit of measure, e.g. pcs, hrs, lot",
    )
    unit_price: float | None = Field(
        default=None,
        description="Price per unit",
    )
    line_total: float | None = Field(
        default=None,
        description="Total amount of this row",
    )


class RawInvoice(BaseModel):
    """Invoice data returned by the extraction service."""

    model_config = ConfigDict(allow_inf_nan=False)

    invoice_number: str | None = Field(
        default=None,
        description="Invoice number / ID",
    )
    invoice_date: str | None = Field(
        default=None,
        description="Invoice date, ISO YYYY-MM-DD",
    )
    due_date: str | None = Field(
        default=None,
        description="Due date, ISO YYYY-MM-DD",
    )
    supplier_name: str | None = Field(
        default=None,
        description="Company issuing the invoice",
    )
    customer_name: str | None = Field(
        default=None,
        description="Company billed",
    )
    currency: str | None = Field(
        default=None,
        description="ISO 4217 currency code, e.g. NPR",
    )
    items: list[RawLineItem] = Field(
        default_factory=list,
        description="Every invoice line item, in printed order",
    )
    subtotal: float | None = Field(
        default=None,
        description="Subtotal before tax",
    )
    tax_rate_percent: float | None = Field(
        default=None,
        description="Tax rate as a percentage, e.g. 13",
    )
    tax_amount: float | None = Field(
        default=None,
        description="Tax amount",
    )
    total_amount: float | None = Field(
        default=None,
        description="Grand total payable",
    )


# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------


class LineItem(BaseModel):
    """A normalized invoice line item."""

    model_config = ConfigDict(allow_inf_nan=False)

    description: str | None = None
    quantity: Decimal | None = None
    unit: str | None = None
    unit_price: Decimal | None = None
    line_total: Decimal | None = None


class Invoice(BaseModel):
    """A normalized invoice ready for business validation."""

    model_config = ConfigDict(allow_inf_nan=False)

    invoice_number: str | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    supplier_name: str | None = None
    customer_name: str | None = None
    currency: str | None = None
    items: list[LineItem] = Field(default_factory=list)
    subtotal: Decimal | None = None
    tax_rate_percent: Decimal | None = None
    tax_amount: Decimal | None = None
    total_amount: Decimal | None = None


class Issue(BaseModel):
    """A business-validation error or warning."""

    level: Literal["error", "warning"]
    code: str
    message: str


class ValidationReport(BaseModel):
    """The result of validating a normalized invoice."""

    passed: bool
    issues: list[Issue] = Field(default_factory=list)


class ExtractionResult(BaseModel):
    """An extracted invoice together with its validation report."""

    invoice: Invoice
    validation: ValidationReport
    model_used: str | None = None


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------


def _dec(
    value: Decimal | float | int | str | None,
) -> Decimal | None:
    """Convert a numeric value to a finite Decimal.

    Invalid and non-finite values become None.

    Commas in string inputs are treated as thousands separators, preserving
    the original helper's behavior. Decimal-comma notation is not supported.
    """
    if value is None or isinstance(value, bool):
        return None

    try:
        if isinstance(value, Decimal):
            result = value
        else:
            text = str(value).strip().replace(",", "")
            if not text:
                return None
            result = Decimal(text)
    except (InvalidOperation, ValueError):
        return None

    return result if result.is_finite() else None


def _date(value: str | None) -> date | None:
    """Parse a complete YYYY-MM-DD date; invalid values become None."""
    value = _clean(value)
    if value is None:
        return None

    if _ISO_DATE_PATTERN.fullmatch(value) is None:
        return None

    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _clean(value: str | None) -> str | None:
    """Strip surrounding whitespace and normalize empty strings to None."""
    if value is None:
        return None

    return value.strip() or None


def _to_line_item(raw: RawLineItem) -> LineItem:
    """Normalize one extracted line item without changing its position."""
    return LineItem(
        description=_clean(raw.description),
        quantity=_dec(raw.quantity),
        unit=_clean(raw.unit),
        unit_price=_dec(raw.unit_price),
        line_total=_dec(raw.line_total),
    )


def to_domain(raw: RawInvoice) -> Invoice:
    """Normalize validated extraction data into an Invoice.

    Unparseable dates and numeric helper inputs become None. Business
    validation remains responsible for reporting missing fields and
    inconsistent amounts.

    This function expects a normally validated RawInvoice instance.
    """
    currency = _clean(raw.currency)

    return Invoice(
        invoice_number=_clean(raw.invoice_number),
        invoice_date=_date(raw.invoice_date),
        due_date=_date(raw.due_date),
        supplier_name=_clean(raw.supplier_name),
        customer_name=_clean(raw.customer_name),
        currency=currency.upper() if currency is not None else None,
        items=[_to_line_item(item) for item in raw.items],
        subtotal=_dec(raw.subtotal),
        tax_rate_percent=_dec(raw.tax_rate_percent),
        tax_amount=_dec(raw.tax_amount),
        total_amount=_dec(raw.total_amount),
    )