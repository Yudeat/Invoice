# AI-Powered Invoice Extractor

A small Python command-line app that reads an invoice image, extracts the key data with
**Google Gemini** (free tier), validates it, and outputs structured JSON.

It extracts: invoice number, invoice date, supplier name, line items (description, quantity,
unit, unit price), and total amount, plus due date, customer, currency, subtotal and VAT.

## Quickstart

Requires Python 3.10+ (3.12 recommended).

```bash
# 1. Install
python3 -m venv .venv            # on Windows: python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e .

# 2. Try it with no API key (offline demo of the full pipeline)
invoice-extractor samples/rivertech_invoice.png --mock

# 3. Real AI extraction with a free Gemini key
cp .env.example .env             # then paste your key into .env
invoice-extractor samples/rivertech_invoice.png
```

Get a free key (no credit card) at <https://aistudio.google.com/apikey>.

> `--mock` returns a fixed built-in response. It does **not** read the image. It exists so the
> pipeline can be run and reviewed without a key.

| Option | Meaning |
|---|---|
| `-o out.json` | write JSON to a file instead of stdout |
| `--compact` | single-line JSON |
| `--mock` | offline demo, no AI call |
| `--version`, `-h` | version / help |

JSON goes to stdout; validation issues and errors go to stderr, so the output can be piped.

## Example output (real Gemini run)

```json
{
  "invoice": {
    "invoice_number": "RT-2024-1052",
    "invoice_date": "2024-10-14",
    "due_date": "2024-11-13",
    "supplier_name": "RIVERTECH SUPPLIES LTD.",
    "customer_name": "Deutschelink GmbH",
    "currency": "NPR",
    "items": [
      {"description": "HDPE Pipe 110mm (6m length)", "quantity": 50, "unit": "pcs",
       "unit_price": 1250, "line_total": 62500}
    ],
    "subtotal": 100500,
    "tax_rate_percent": 13,
    "tax_amount": 13065,
    "total_amount": 113565
  },
  "validation": {"passed": true, "issues": []},
  "model_used": "gemini-3.5-flash"
}
```

The full output lists all five line items. See `samples/expected_output.json`.

## How it works

```
image -> size + file-signature check
      -> Gemini vision call (JSON schema enforced, temperature 0)
      -> RawInvoice (Pydantic) -> domain model (Decimal money, real dates)
      -> business-rule validation -> JSON + exit code
```

| File | Responsibility |
|---|---|
| `extractor.py` | image loading, Gemini call, retries, model fallback |
| `models.py` | AI-facing schema and domain models, normalisation |
| `validation.py` | business rules, independent of the AI |
| `cli.py` | arguments, JSON output, exit codes |
| `mock.py` | offline demo response |

## Validation

- Required fields: invoice number, date, supplier, total, and at least one line item
- Per line: `quantity x unit_price == line_total`
- Sum of line totals `== subtotal`
- `tax_rate% x subtotal == tax_amount`
- `subtotal + tax == total_amount`
- Due date is not before the invoice date

Errors fail validation; warnings (for example, an item missing a price) are reported but do not.
Amounts use `Decimal` with a 0.01 tolerance. Checks are skipped when the data they need is
missing, and that is reported rather than assumed.

## Error handling

- The prompt tells the model to return `null` instead of guessing. Missing or unparseable values
  become `null` in the JSON and appear in `validation.issues`; the app does not crash on them.
- Missing, empty, oversized or unsupported images give a clear message. The format is checked
  from the file's bytes, not its extension.
- Rate limits and server errors (429/5xx) are retried with exponential backoff, then the next
  model in the fallback list is tried.
- A missing or rejected API key gives an actionable message.

**Exit codes:** `0` valid, `1` extracted but validation found errors (JSON still printed),
`2` could not extract (bad input, configuration or AI failure).

## Design decisions

- **Enforced JSON schema, not "please reply in JSON".** The API constrains the output and Pydantic
  re-validates it, so there is no regex or fragile text parsing.
- **Two schemas.** The AI sees plain floats and strings; the rest of the app uses `Decimal` and `date`.
- **Validation is separate from extraction.** It is plain code that can be tested without any AI.
- **Model fallback.** Free-tier model names change, so set `GEMINI_MODELS=model1,model2` in `.env`
  to override the default order.
- **Mock mode.** Anyone can run and review the pipeline without a key.

## Docker

```bash
docker build -t invoice-extractor .
docker run --rm invoice-extractor                      # offline demo
docker run --rm -e GEMINI_API_KEY \
  invoice-extractor /app/samples/rivertech_invoice.png # real extraction
```

## Tests

```bash
pip install -e ".[dev]"
pytest
```

27 tests cover the validation rules (including deliberately wrong totals), the extractor with a
fake client (retries, model fallback, bad key, empty or malformed responses), input checks and the
CLI. They never call the real API, so they do not measure extraction accuracy.

## Limitations and next steps

- The model can misread amounts or miss rows. Arithmetic checks catch inconsistent numbers, but
  cannot prove the output matches the image. Review results before using them for payments.
- Invoice contents are sent to Google for real extraction, so check data-handling terms for
  sensitive documents.
- The total check assumes `subtotal + tax = total`; discounts, withholding and multiple taxes
  are not modelled.
- Single PNG/JPEG/WEBP images only. Next: PDF and multi-page support, a `--batch folder/` mode,
  and a human-review step for invoices that fail validation.