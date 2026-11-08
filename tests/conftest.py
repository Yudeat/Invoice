"""Shared fixtures for invoice-extractor tests."""

from pathlib import Path

import pytest

from invoice_extractor.mock import mock_raw_invoice
from invoice_extractor.models import Invoice, to_domain


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE = PROJECT_ROOT / "samples" / "rivertech_invoice.png"


@pytest.fixture
def sample_image() -> Path:
    """Return the sample image path, failing clearly if it is missing."""
    if not SAMPLE.is_file():
        pytest.fail(
            f"Sample invoice image is missing or is not a file: {SAMPLE}",
            pytrace=False,
        )

    return SAMPLE


@pytest.fixture
def good_invoice() -> Invoice:
    """Return a fresh invoice built from the mock extraction response."""
    return to_domain(mock_raw_invoice())