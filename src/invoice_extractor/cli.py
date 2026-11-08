from __future__ import annotations

import argparse
import json
import math
import sys
from decimal import Decimal, DecimalException
from pathlib import Path
from typing import Any

from . import __version__
from .errors import InvoiceError
from .models import ExtractionResult, to_domain
from .validation import validate


_MONEY_KEYS = frozenset(
    {
        "quantity",
        "unit_price",
        "line_total",
        "subtotal",
        "tax_rate_percent",
        "tax_amount",
        "total_amount",
    }
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="invoice-extractor",
        description=(
            "Extract structured data from an invoice image using Gemini "
            "and validate it."
        ),
    )
    parser.add_argument(
        "image",
        type=Path,
        help="Path to the invoice image (PNG, JPEG or WEBP)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Write JSON to this file instead of stdout",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Offline demo: skip the AI call and use a built-in response",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Compact JSON instead of pretty-printed",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def run(args: argparse.Namespace) -> int:
    """Run extraction.

    Exit codes:
        0: Extraction completed and validation passed.
        1: Extraction completed but validation failed.
        2: Extraction, conversion, serialization, or output failed.
    """
    try:
        if args.mock:
            from .extractor import load_image
            from .mock import mock_raw_invoice

            # Mock mode still checks that the supplied image is valid.
            load_image(args.image)
            raw, model = mock_raw_invoice(), "mock"
        else:
            from dotenv import load_dotenv

            from .extractor import extract_invoice

            load_dotenv()
            raw, model = extract_invoice(args.image)

        invoice = to_domain(raw)
        result = ExtractionResult(
            invoice=invoice,
            validation=validate(invoice),
            model_used=model,
        )
        text = _dump(result, compact=args.compact)

    except (InvoiceError, OSError, ValueError, DecimalException) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    try:
        if args.output is not None:
            args.output.write_text(text + "\n", encoding="utf-8")
            print(f"Wrote {args.output}", file=sys.stderr)
        else:
            print(text)
    except OSError as exc:
        destination = (
            f"output file '{args.output}'"
            if args.output is not None
            else "stdout"
        )
        print(f"Error: Cannot write to {destination}: {exc}", file=sys.stderr)
        return 2

    for issue in result.validation.issues:
        print(
            f"[{issue.level.upper()}] {issue.code}: {issue.message}",
            file=sys.stderr,
        )

    return 0 if result.validation.passed else 1


def _dump(result: ExtractionResult, *, compact: bool) -> str:
    """Serialize the result, keeping dates as ISO strings and money as numbers."""
    data = json.loads(result.model_dump_json())
    _numberise(data)

    return json.dumps(
        data,
        indent=None if compact else 2,
        separators=(",", ":") if compact else None,
        ensure_ascii=False,
        allow_nan=False,
    )


def _numberise(node: Any) -> None:
    """Convert Decimal strings in known numeric fields to JSON numbers.

    Integral values use integers. Fractional values use floats to preserve
    the existing output contract, so arbitrary Decimal precision is not
    guaranteed.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            if key in _MONEY_KEYS and isinstance(value, str):
                decimal_value = Decimal(value)

                if not decimal_value.is_finite():
                    raise ValueError(
                        f"Field '{key}' must contain a finite number."
                    )

                if decimal_value == decimal_value.to_integral_value():
                    node[key] = int(decimal_value)
                else:
                    numeric_value = float(decimal_value)

                    if not math.isfinite(numeric_value):
                        raise ValueError(
                            f"Field '{key}' is outside the supported "
                            "JSON number range."
                        )

                    node[key] = numeric_value
            else:
                _numberise(value)

    elif isinstance(node, list):
        for item in node:
            _numberise(item)


def main(argv: list[str] | None = None) -> None:
    sys.exit(run(build_parser().parse_args(argv)))


if __name__ == "__main__":
    main()