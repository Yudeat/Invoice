"""Tests for image loading and invoice extraction.

All extraction requests use scripted fake clients; no network calls are made.
"""

import json
from types import SimpleNamespace

import pytest
from google.genai import errors as genai_errors
from httpx import ConnectError

from invoice_extractor import extractor
from invoice_extractor.errors import (
    ConfigError,
    ExtractionError,
    InvalidInputError,
)
from invoice_extractor.extractor import (
    detect_mime,
    extract_invoice,
    load_image,
)
from invoice_extractor.mock import mock_raw_invoice


GOOD = mock_raw_invoice().model_dump_json()


class FakeModels:
    """Replay scripted responses and record model requests."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def generate_content(self, *, model, contents, config):
        self.calls.append(model)

        if not self.outcomes:
            raise AssertionError(
                f"Unexpected request for model {model!r}: "
                "no scripted outcomes remain."
            )

        outcome = self.outcomes.pop(0)

        if isinstance(outcome, Exception):
            raise outcome

        return SimpleNamespace(text=outcome)


class FakeClient:
    """Provide the SDK interface used by the extractor."""

    def __init__(self, outcomes):
        self.models = FakeModels(outcomes)
        self.closed = False

    def close(self):
        self.closed = True


def api_error(code):
    return genai_errors.APIError(
        code,
        {
            "error": {
                "code": code,
                "message": "Scripted API failure",
                "status": "UNKNOWN",
            }
        },
    )


def no_sleep(_):
    """Disable actual backoff delays in tests."""


def test_happy_path(sample_image):
    client = FakeClient([GOOD])

    raw, model = extract_invoice(
        sample_image,
        client=client,
        models=["m1"],
        sleep=no_sleep,
    )

    assert raw.invoice_number == "RT-2024-1052"
    assert model == "m1"
    assert client.models.calls == ["m1"]
    assert client.closed is False


def test_retries_on_rate_limit_then_succeeds(sample_image):
    client = FakeClient([api_error(429), api_error(503), GOOD])
    delays = []

    raw, model = extract_invoice(
        sample_image,
        client=client,
        models=["m1"],
        sleep=delays.append,
    )

    assert raw.total_amount == 113565
    assert model == "m1"
    assert client.models.calls == ["m1", "m1", "m1"]
    assert delays == [2.0, 4.0]


def test_falls_back_to_next_model_on_404(sample_image):
    client = FakeClient([api_error(404), GOOD])
    delays = []

    _, model = extract_invoice(
        sample_image,
        client=client,
        models=["old", "new"],
        sleep=delays.append,
    )

    assert model == "new"
    assert client.models.calls == ["old", "new"]
    assert delays == []


@pytest.mark.parametrize("status_code", [401, 403])
def test_auth_failure_raises_config_error(sample_image, status_code):
    client = FakeClient([api_error(status_code)])
    delays = []

    with pytest.raises(ConfigError):
        extract_invoice(
            sample_image,
            client=client,
            models=["m1", "m2"],
            sleep=delays.append,
        )

    assert client.models.calls == ["m1"]
    assert delays == []
    assert client.closed is False


def test_all_models_fail_raises_extraction_error(sample_image):
    client = FakeClient([api_error(503) for _ in range(6)])
    delays = []

    with pytest.raises(ExtractionError, match="AI extraction failed"):
        extract_invoice(
            sample_image,
            client=client,
            models=["a", "b"],
            sleep=delays.append,
        )

    assert client.models.calls == ["a", "a", "a", "b", "b", "b"]
    assert delays == [2.0, 4.0, 2.0, 4.0]
    assert client.closed is False


def test_transport_failure_is_retried(sample_image):
    client = FakeClient([ConnectError("Connection failed"), GOOD])
    delays = []

    _, model = extract_invoice(
        sample_image,
        client=client,
        models=["m1"],
        sleep=delays.append,
    )

    assert model == "m1"
    assert client.models.calls == ["m1", "m1"]
    assert delays == [2.0]


def test_programming_error_is_not_retried(sample_image):
    client = FakeClient([TypeError("Unexpected programming error")])
    delays = []

    with pytest.raises(TypeError, match="Unexpected programming error"):
        extract_invoice(
            sample_image,
            client=client,
            models=["m1"],
            sleep=delays.append,
        )

    assert client.models.calls == ["m1"]
    assert delays == []


@pytest.mark.parametrize("response", [None, "", "   "])
def test_empty_response_falls_back_to_next_model(sample_image, response):
    client = FakeClient([response, GOOD])
    delays = []

    _, model = extract_invoice(
        sample_image,
        client=client,
        models=["a", "b"],
        sleep=delays.append,
    )

    assert model == "b"
    assert client.models.calls == ["a", "b"]
    assert delays == []


def test_invalid_json_is_retried_then_succeeds(sample_image):
    client = FakeClient(["not json", GOOD])
    delays = []

    raw, model = extract_invoice(
        sample_image,
        client=client,
        models=["m1"],
        sleep=delays.append,
    )

    assert raw.invoice_number == "RT-2024-1052"
    assert model == "m1"
    assert client.models.calls == ["m1", "m1"]
    assert delays == [2.0]


def test_empty_and_garbage_responses_fail(sample_image):
    client = FakeClient([None, "not json", "not json", "not json"])

    with pytest.raises(ExtractionError, match="schema"):
        extract_invoice(
            sample_image,
            client=client,
            models=["a", "b"],
            sleep=no_sleep,
        )

    assert client.models.calls == ["a", "b", "b", "b"]


def test_partial_ai_output_is_accepted(sample_image):
    partial = json.dumps({"invoice_number": "X-1"})
    client = FakeClient([partial])

    raw, model = extract_invoice(
        sample_image,
        client=client,
        models=["m"],
        sleep=no_sleep,
    )

    assert raw.invoice_number == "X-1"
    assert raw.items == []
    assert raw.total_amount is None
    assert model == "m"


@pytest.mark.parametrize("retries", [0, -1, True, 1.5, "3"])
def test_invalid_retry_count_is_rejected(sample_image, retries):
    client = FakeClient([])

    with pytest.raises(ConfigError, match="positive integer"):
        extract_invoice(
            sample_image,
            client=client,
            models=["m1"],
            retries=retries,
            sleep=no_sleep,
        )

    assert client.models.calls == []


@pytest.mark.parametrize("models", [[], [""], [" "], ["m1", ""]])
def test_invalid_model_list_is_rejected(sample_image, models):
    client = FakeClient([])

    with pytest.raises(ConfigError, match="model name"):
        extract_invoice(
            sample_image,
            client=client,
            models=models,
            sleep=no_sleep,
        )

    assert client.models.calls == []


@pytest.mark.parametrize("fails", [False, True])
def test_internally_created_client_is_closed(
    sample_image,
    monkeypatch,
    fails,
):
    client = FakeClient([api_error(503)] if fails else [GOOD])
    monkeypatch.setattr(extractor, "_get_client", lambda: client)

    if fails:
        with pytest.raises(ExtractionError):
            extract_invoice(
                sample_image,
                models=["m1"],
                retries=1,
                sleep=no_sleep,
            )
    else:
        extract_invoice(
            sample_image,
            models=["m1"],
            retries=1,
            sleep=no_sleep,
        )

    assert client.closed is True


def test_missing_file_rejected(tmp_path):
    with pytest.raises(InvalidInputError, match="not found"):
        load_image(tmp_path / "missing.png")


def test_directory_rejected(tmp_path):
    with pytest.raises(InvalidInputError, match="Not a file"):
        load_image(tmp_path)


def test_non_image_rejected(tmp_path):
    path = tmp_path / "fake.png"
    path.write_bytes(b"%PDF-1.4 not an image")

    with pytest.raises(InvalidInputError, match="Unsupported"):
        load_image(path)


def test_empty_file_rejected(tmp_path):
    path = tmp_path / "empty.png"
    path.write_bytes(b"")

    with pytest.raises(InvalidInputError, match="empty"):
        load_image(path)


def test_oversized_file_rejected(tmp_path, monkeypatch):
    # Use a small limit rather than allocating a large fixture.
    monkeypatch.setattr(extractor, "MAX_BYTES", 16)
    path = tmp_path / "large.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 9)

    with pytest.raises(InvalidInputError, match="too large"):
        load_image(path)


def test_load_image_returns_bytes_and_mime(sample_image):
    data, mime = load_image(sample_image)

    assert data == sample_image.read_bytes()
    assert mime == "image/png"


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (b"\x89PNG\r\n\x1a\n", "image/png"),
        (b"\xff\xd8\xff\xe0abc", "image/jpeg"),
        (b"RIFF\x00\x00\x00\x00WEBP", "image/webp"),
        (b"RIFF", None),
        (b"RIFF\x00\x00\x00\x00WAVE", None),
        (b"hello", None),
        (b"", None),
    ],
)
def test_mime_sniffing(data, expected):
    assert detect_mime(data) == expected