"""Business-rule validation, independent of extraction.

Checks that require missing data are skipped. Missing required invoice fields
are errors; missing optional data may produce warnings.

Amounts use a fixed 0.01 tolerance and two-decimal tax rounding. These are
application policies, not currency-specific accounting rules.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from .models import Invoice, Issue, LineItem, ValidationReport


TOLERANCE = Decimal("0.01")
CENT = Decimal("0.01")
ZERO = Decimal("0")
HUNDRED = Decimal("100")

REQUIRED_FIELDS = (
    "invoice_number",
    "invoice_date",
    "supplier_name",
    "total_amount",
)


def _close(a: Decimal, b: Decimal) -> bool:
    """Return whether two amounts differ by no more than the tolerance."""
    return abs(a - b) <= TOLERANCE


def _err(code: str, msg: str) -> Issue:
    return Issue(level="error", code=code, message=msg)


def _warn(code: str, msg: str) -> Issue:
    return Issue(level="warning", code=code, message=msg)


def _missing(value: object) -> bool:
    """Treat None and whitespace-only strings as missing values."""
    return value is None or (
        isinstance(value, str) and not value.strip()
    )


def _validate_required_fields(inv: Invoice) -> list[Issue]:
    issues: list[Issue] = []

    for field in REQUIRED_FIELDS:
        if _missing(getattr(inv, field)):
            issues.append(
                _err(
                    f"MISSING_{field.upper()}",
                    f"Required field '{field}' was not found.",
                )
            )

    if not inv.items:
        issues.append(_err("NO_ITEMS", "No line items were found."))

    return issues


def _validate_line_item(item: LineItem, number: int) -> list[Issue]:
    issues: list[Issue] = []
    label = f"Item {number}"

    if not _missing(item.description):
        label += f" ({item.description})"
    else:
        issues.append(
            _warn(
                "ITEM_NO_DESCRIPTION",
                f"Item {number} has no description.",
            )
        )

    missing_operands = (
        item.quantity is None or item.unit_price is None
    )

    if missing_operands:
        issues.append(
            _warn(
                "ITEM_INCOMPLETE",
                f"{label}: quantity or unit price missing.",
            )
        )

    # Check available values independently, even if another value is missing.
    if (
        item.quantity is not None and item.quantity < ZERO
    ) or (
        item.unit_price is not None and item.unit_price < ZERO
    ):
        issues.append(
            _warn(
                "ITEM_NEGATIVE",
                f"{label}: negative quantity or price.",
            )
        )

    if item.line_total is None:
        issues.append(
            _warn(
                "ITEM_NO_TOTAL",
                f"{label}: line total missing.",
            )
        )

    if (
        item.quantity is not None
        and item.unit_price is not None
        and item.line_total is not None
    ):
        expected = item.quantity * item.unit_price

        if not _close(expected, item.line_total):
            issues.append(
                _err(
                    "LINE_MISMATCH",
                    f"{label}: {item.quantity} x {item.unit_price} "
                    f"= {expected}, but line total is {item.line_total}.",
                )
            )

    return issues


def _complete_items_sum(inv: Invoice) -> Decimal | None:
    """Sum line totals only when every item has a total.

    A partial sum is not a reliable subtotal or tax base.
    """
    if not inv.items:
        return None

    total = ZERO

    for item in inv.items:
        if item.line_total is None:
            return None
        total += item.line_total

    return total


def _validate_amounts(
    inv: Invoice,
    items_sum: Decimal | None,
) -> list[Issue]:
    issues: list[Issue] = []

    if items_sum is not None and inv.subtotal is not None:
        if not _close(items_sum, inv.subtotal):
            issues.append(
                _err(
                    "SUBTOTAL_MISMATCH",
                    f"Line totals add up to {items_sum}, "
                    f"but subtotal is {inv.subtotal}.",
                )
            )

    base = inv.subtotal if inv.subtotal is not None else items_sum

    if (
        base is not None
        and inv.tax_rate_percent is not None
        and inv.tax_amount is not None
    ):
        expected_tax = (
            base * inv.tax_rate_percent / HUNDRED
        ).quantize(CENT, rounding=ROUND_HALF_UP)

        if not _close(expected_tax, inv.tax_amount):
            issues.append(
                _err(
                    "TAX_MISMATCH",
                    f"{inv.tax_rate_percent}% of {base} is "
                    f"{expected_tax}, but tax amount is "
                    f"{inv.tax_amount}.",
                )
            )

    if inv.total_amount is None:
        return issues

    if base is None:
        issues.append(
            _warn(
                "TOTAL_UNVERIFIED",
                "Could not verify total: no complete base amount "
                "is available.",
            )
        )
        return issues

    if inv.tax_amount is None:
        issues.append(
            _warn(
                "TOTAL_UNVERIFIED",
                "Could not verify total: tax amount is missing "
                "and cannot safely be assumed to be zero.",
            )
        )
        return issues

    expected_total = base + inv.tax_amount

    if not _close(expected_total, inv.total_amount):
        issues.append(
            _err(
                "TOTAL_MISMATCH",
                f"Subtotal + tax = {expected_total}, "
                f"but total amount is {inv.total_amount}.",
            )
        )

    return issues


def _validate_dates(inv: Invoice) -> list[Issue]:
    issues: list[Issue] = []

    if inv.invoice_date is not None and inv.due_date is not None:
        if inv.due_date < inv.invoice_date:
            issues.append(
                _err(
                    "DATE_ORDER",
                    "Due date is before the invoice date.",
                )
            )
    elif inv.invoice_date is None and inv.due_date is not None:
        issues.append(
            _warn(
                "DATE_PARTIAL",
                "Due date found but invoice date missing.",
            )
        )

    return issues


def validate(inv: Invoice) -> ValidationReport:
    """Validate a normalized invoice without modifying it.

    Errors cause validation to fail. Warnings indicate missing data or
    checks that could not be completed.

    This expects a normally validated Invoice with finite Decimal values.
    """
    issues = _validate_required_fields(inv)

    for number, item in enumerate(inv.items, start=1):
        issues.extend(_validate_line_item(item, number))

    items_sum = _complete_items_sum(inv)
    issues.extend(_validate_amounts(inv, items_sum))
    issues.extend(_validate_dates(inv))

    if _missing(inv.currency):
        issues.append(
            _warn(
                "MISSING_CURRENCY",
                "Currency was not detected.",
            )
        )

    return ValidationReport(
        passed=not any(issue.level == "error" for issue in issues),
        issues=issues,
    )