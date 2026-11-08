"""Tests for the invoice-extractor command-line interface."""

import json

import pytest

from invoice_extractor import __version__
from invoice_extractor.cli import main


def run_cli(argv, capsys):
    """Invoke the CLI and return its exit code and captured output."""
    with pytest.raises(SystemExit) as exc_info:
        main(argv)

    return exc_info.value.code, capsys.readouterr()


def test_mock_run_outputs_valid_json(sample_image, capsys):
    code, captured = run_cli(
        [str(sample_image), "--mock"],
        capsys,
    )

    assert code == 0

    data = json.loads(captured.out)

    assert data["validation"]["passed"] is True
    assert data["model_used"] == "mock"
    assert data["invoice"]["total_amount"] == 113565
    assert data["invoice"]["items"][0]["quantity"] == 50


def test_output_file(sample_image, tmp_path, capsys):
    target = tmp_path / "out.json"

    code, captured = run_cli(
        [str(sample_image), "--mock", "-o", str(target)],
        capsys,
    )

    assert code == 0
    assert captured.out == ""
    assert f"Wrote {target}" in captured.err

    text = target.read_text(encoding="utf-8")
    data = json.loads(text)

    assert text.endswith("\n")
    assert data["invoice"]["invoice_number"] == "RT-2024-1052"


def test_compact_output(sample_image, capsys):
    code, captured = run_cli(
        [str(sample_image), "--mock", "--compact"],
        capsys,
    )

    assert code == 0

    data = json.loads(captured.out)
    expected = json.dumps(
        data,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )

    assert captured.out == expected + "\n"


def test_missing_file_exit_code_2(tmp_path, capsys):
    missing = tmp_path / "missing.png"

    code, captured = run_cli(
        [str(missing), "--mock"],
        capsys,
    )

    assert code == 2
    assert captured.out == ""
    assert "not found" in captured.err.lower()


def test_empty_file_exit_code_2(tmp_path, capsys):
    empty = tmp_path / "empty.png"
    empty.write_bytes(b"")

    code, captured = run_cli(
        [str(empty), "--mock"],
        capsys,
    )

    assert code == 2
    assert captured.out == ""
    assert "empty" in captured.err.lower()


def test_unsupported_image_exit_code_2(tmp_path, capsys):
    invalid = tmp_path / "invalid.png"
    invalid.write_bytes(b"This is not an image.")

    code, captured = run_cli(
        [str(invalid), "--mock"],
        capsys,
    )

    assert code == 2
    assert captured.out == ""
    assert "unsupported" in captured.err.lower()


def test_missing_api_key_exit_code_2(
    sample_image,
    monkeypatch,
    capsys,
):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    # Prevent local .env credentials from affecting this test.
    monkeypatch.setattr(
        "dotenv.load_dotenv",
        lambda *args, **kwargs: False,
    )

    code, captured = run_cli(
        [str(sample_image)],
        capsys,
    )

    assert code == 2
    assert captured.out == ""
    assert "GEMINI_API_KEY" in captured.err


def test_output_write_failure_exit_code_2(
    sample_image,
    tmp_path,
    capsys,
):
    # A directory cannot be used as an output file. This avoids relying
    # on platform-specific permission behavior.
    code, captured = run_cli(
        [str(sample_image), "--mock", "-o", str(tmp_path)],
        capsys,
    )

    assert code == 2
    assert captured.out == ""
    assert "Cannot write" in captured.err
    assert "Traceback" not in captured.err


def test_validation_failure_exit_code_1(
    sample_image,
    monkeypatch,
    capsys,
):
    from invoice_extractor.mock import mock_raw_invoice

    raw = mock_raw_invoice()
    raw.invoice_number = None

    monkeypatch.setattr(
        "invoice_extractor.mock.mock_raw_invoice",
        lambda: raw,
    )

    code, captured = run_cli(
        [str(sample_image), "--mock"],
        capsys,
    )

    assert code == 1

    data = json.loads(captured.out)

    assert data["validation"]["passed"] is False
    assert any(
        issue["code"] == "MISSING_INVOICE_NUMBER"
        for issue in data["validation"]["issues"]
    )
    assert "[ERROR] MISSING_INVOICE_NUMBER:" in captured.err


def test_version(capsys):
    code, captured = run_cli(["--version"], capsys)

    assert code == 0
    assert captured.out.strip() == f"invoice-extractor {__version__}"
    assert captured.err == ""


def test_missing_image_argument_exit_code_2(capsys):
    code, captured = run_cli([], capsys)

    assert code == 2
    assert captured.out == ""
    assert "usage:" in captured.err.lower()