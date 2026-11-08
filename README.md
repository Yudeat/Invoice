# AI-Powered Invoice Extractor

A Python command-line application that extracts structured invoice data from images using **Google Gemini**, validates business rules, and outputs JSON.

Includes an offline mock mode for demonstrating the pipeline without an API key or network request.

> **Status:** Prototype for development and evaluation. Review extracted data before using it for payments, tax reporting, or accounting records.

## Features

- PNG, JPEG, and WEBP input, up to 10 MB.
- Invoice details, supplier, customer, dates, currency, and line items.
- Subtotal, tax rate, tax amount, and grand total extraction.
- Structured AI output validated with Pydantic.
- Domain models using `Decimal` amounts and real dates.
- Business-rule validation with errors and warnings.
- Retries and configurable model fallback.
- JSON output to stdout or a file.
- Offline mock mode.

## Requirements

- Python 3.12 recommended, matching the Docker image.
- See `requires-python` in `pyproject.toml` for supported Python versions.
- Gemini API key and internet access for real extraction.
- Docker, optionally.

Model availability, pricing, and quotas depend on your Gemini project and selected models. Check the provider’s current documentation before deployment.

## Installation

Run these commands from the project root.

### Create a virtual environment

```bash
python -m venv .venv
```

Activate on macOS or Linux:

```bash
source .venv/bin/activate
```

Activate on Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

### Install

```bash
python -m pip install -e .
```

### Verify installation

```bash
invoice-extractor --version
invoice-extractor --help
```

## Quickstart

### Offline demo

```bash
invoice-extractor samples/rivertech_invoice.png --mock
```

Mock mode checks the input file and returns a fixed built-in invoice response.

**It does not extract information from the supplied image.** A different supported image will still produce the same mock invoice.

### Real extraction

Create a Gemini API key through Google AI Studio.

Copy the environment template:

```bash
cp .env.example .env
```

Set your key in `.env`:

```dotenv
GEMINI_API_KEY=your_api_key_here
```

Run extraction:

```bash
invoice-extractor samples/rivertech_invoice.png
```

Alternatively, set the key in your shell:

```bash
export GEMINI_API_KEY="your_api_key_here"
```

The application also accepts `GOOGLE_API_KEY`. A non-empty `GEMINI_API_KEY` takes precedence.

> Never commit API keys or `.env` files.

## Usage

```text
invoice-extractor IMAGE [OPTIONS]
```

| Option | Description |
|---|---|
| `-o`, `--output PATH` | Write JSON to a file |
| `--compact` | Emit compact, single-line JSON |
| `--mock` | Use the fixed offline response |
| `--version` | Print the application version |
| `-h`, `--help` | Show help |

### Save output

```bash
mkdir -p output

invoice-extractor samples/rivertech_invoice.png \
  -o output/invoice.json
```

The output directory must already exist.

### Compact JSON

```bash
invoice-extractor samples/rivertech_invoice.png \
  --mock \
  --compact
```

### Separate JSON and diagnostics

JSON is written to stdout. Errors, validation issues, and file-write notifications go to stderr.

```bash
invoice-extractor samples/rivertech_invoice.png \
  > invoice.json \
  2> invoice.log
```

## Configuration

| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY` | Preferred API key |
| `GOOGLE_API_KEY` | Alternative API key |
| `GEMINI_MODELS` | Comma-separated model preference list |

Example:

```dotenv
GEMINI_API_KEY=your_api_key_here
GEMINI_MODELS=your_primary_model,your_fallback_model
```

Replace the model placeholders with actual image-capable models available to your project.

Models are attempted in order. Do not assume the built-in model names will remain available indefinitely.

## Docker

### Build

```bash
docker build -t invoice-extractor .
```

### Run the offline demo

```bash
docker run --rm invoice-extractor
```

### Run real extraction

Set `GEMINI_API_KEY` in the host environment, then run:

```bash
docker run --rm \
  -e GEMINI_API_KEY \
  invoice-extractor \
  /app/samples/rivertech_invoice.png
```

### Process a host image

Example for macOS or Linux:

```bash
docker run --rm \
  -e GEMINI_API_KEY \
  --mount type=bind,source="$(pwd)/samples",target=/input,readonly \
  invoice-extractor \
  /input/rivertech_invoice.png
```

### Save output on the host

```bash
docker run --rm \
  -e GEMINI_API_KEY \
  --mount type=bind,source="$(pwd)/samples",target=/input,readonly \
  invoice-extractor \
  /input/rivertech_invoice.png \
  > invoice.json
```

Host shell redirection avoids output-directory permission issues inside the container.

Do not copy `.env` into the Docker image. Supply credentials at runtime.

## Example Output

Abridged mock output:

```json
{
  "invoice": {
    "invoice_number": "RT-2024-1052",
    "invoice_date": "2024-10-14",
    "supplier_name": "RiverTech Supplies Ltd.",
    "items": [
      {
        "description": "HDPE Pipe 110mm (6m length)",
        "quantity": 50,
        "unit": "pcs",
        "unit_price": 1250,
        "line_total": 62500
      }
    ],
    "subtotal": 100500,
    "tax_rate_percent": 13,
    "tax_amount": 13065,
    "total_amount": 113565
  },
  "validation": {
    "passed": true,
    "issues": []
  },
  "model_used": "mock"
}
```

The full response includes additional fields and all invoice line items.

## How It Works

```text
Image
  -> Bounded file read and signature check
  -> Gemini request with structured-output schema
  -> RawInvoice validation
  -> Domain normalization
  -> Business-rule validation
  -> JSON output and exit code
```

| Module | Responsibility |
|---|---|
| `extractor.py` | Image loading, extraction, retries, and fallback |
| `models.py` | AI schemas, domain models, and normalization |
| `validation.py` | Business-rule checks |
| `cli.py` | Arguments, serialization, output, and exit codes |
| `errors.py` | Expected application exceptions |
| `mock.py` | Fixed offline response |

## Validation

Checks include:

- Required invoice number, invoice date, supplier, and total.
- At least one line item.
- Quantity multiplied by unit price matches line total.
- Complete line-total sum matches subtotal.
- Tax rate applied to the available base matches tax amount.
- Subtotal plus known tax matches total.
- Due date is not before invoice date.

### Missing data

Checks are skipped when necessary inputs are unavailable.

- Missing tax is not assumed to be zero.
- Partial line totals are not treated as a complete subtotal.
- Invalid date strings become `null` during normalization.
- Incomplete items and unverified totals produce warnings.

### Amount policy

Comparisons use an absolute tolerance of `0.01`.

Expected tax is rounded to two decimal places using `ROUND_HALF_UP`.

These are fixed application policies, not currency-specific accounting rules.

> `validation.passed: true` means no errors were found. It does not mean every calculation was verified or every extracted field is correct.

## Exit Codes

| Code | Meaning |
|---|---|
| `0` | Extraction completed; no validation errors |
| `1` | Extraction completed; validation errors found |
| `2` | Expected extraction, configuration, conversion, serialization, or output failure |

JSON is still emitted when validation fails with exit code `1`.

Warnings do not cause a nonzero validation exit code.

## Error Handling

Expected errors include:

- Missing, empty, unreadable, oversized, or unsupported files.
- Missing credentials or dependencies.
- Authentication and permission failures.
- Exhausted extraction attempts.
- Output write failures.

Selected API and transport failures are retried with exponential backoff.

The default is three attempts per model, with retry delays of two and four seconds.

Unexpected programming errors are not deliberately hidden or retried.

## Tests

If the project defines a `dev` dependency extra:

```bash
python -m pip install -e ".[dev]"
```

Run all tests:

```bash
python -m pytest -q
```

Run individual suites:

```bash
python -m pytest tests/test_cli.py -q
python -m pytest tests/test_extractor.py -q
python -m pytest tests/test_validation.py -q
```

Extraction tests use fake clients rather than real API requests.

Coverage includes CLI behavior, input validation, retries, fallback, client ownership, missing data, arithmetic checks, and tolerance boundaries.

Mocked tests do not measure real-world extraction accuracy.

## Drawbacks and Limitations

### AI accuracy

The model can misread amounts, omit rows, or identify the wrong supplier. Schema validation and arithmetic checks cannot prove that the response matches the image.

### Financial precision

The AI boundary uses floats. Domain conversion uses `Decimal`, but cannot recover precision already lost.

Fractional Decimal amounts are also converted to floats for JSON output. Exact arbitrary precision is not preserved end to end.

### Limited accounting model

The total equation assumes:

```text
subtotal + tax = total
```

Separate discounts, shipping, withholding, fees, deposits, and multiple tax components are not represented.

### Limited inputs

Only single PNG, JPEG, and WEBP images are supported.

PDFs, multi-page invoices, and batch processing are not implemented.

Signature checking does not fully decode or verify image integrity.

### Incomplete verification

An invoice can pass with warnings when some calculations cannot be checked.

### Cloud dependency and sensitive data

Real extraction sends invoice contents to Google.

Review applicable provider data-use terms, confidentiality requirements, and retention policies before submitting sensitive documents.

### Operational limits

The application does not yet provide explicit end-to-end deadlines, persistent jobs, concurrency controls, cost budgets, or a human-review workflow.

### Output reliability

Direct file writes are not atomic. A failed write can leave a partial output file or damage an existing one.

## Production Improvement Roadmap

### 1. Financial correctness and review

- Preserve exact decimal values through parsing and serialization.
- Add discounts, adjustments, shipping, and multiple taxes.
- Configure rounding and tolerance by currency and business policy.
- Distinguish passed, failed, and incomplete validation.
- Require review for incomplete or suspicious invoices.
- Evaluate against a representative labeled invoice dataset.

### 2. Reliability and security

- Configure request timeouts and overall deadlines.
- Add retry jitter and quota-aware concurrency.
- Avoid overlapping SDK and application retry policies.
- Fully decode images with safe dimension and resource limits.
- Store credentials in a managed secret store.
- Define retention and access policies.
- Redact sensitive data from logs.
- Write output files atomically.

### 3. Observability and deployment

- Add structured logs and request identifiers.
- Record model, prompt, schema, and application versions.
- Track latency, retries, failures, and API usage.
- Pin dependencies and container images.
- Run as a non-root user.
- Add CI tests, container smoke tests, and dependency scanning.

### 4. Workflow and scale

- Add PDF and multi-page support.
- Add batch processing with bounded concurrency.
- Introduce durable, resumable jobs.
- Detect duplicate invoices.
- Build a review interface with source-image references.
- Integrate with accounting systems after approval.

## Troubleshooting

| Problem | Action |
|---|---|
| CLI command not found | Activate the virtual environment and reinstall |
| Missing API key | Set `GEMINI_API_KEY` or `GOOGLE_API_KEY` |
| Model unavailable | Update `GEMINI_MODELS` |
| Rate-limit failures | Reduce request frequency and check quotas |
| Unsupported image | Use an actual supported image format |
| Cannot write output | Check the directory exists and is writable |
| Exit code `1` | Inspect `validation.issues` and stderr |
| `TOTAL_UNVERIFIED` | Provide a complete base amount and explicit tax |
| Mock ignores image contents | Expected: mock returns a fixed response |

## Verification

Run the tests and Docker smoke checks in the actual repository before deployment.

Do not claim a passing test count, verified build, or production readiness until those checks have completed successfully.