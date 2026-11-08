"""Expected, user-facing exceptions for invoice extraction."""


class InvoiceError(Exception):
    """Base class for all expected, user-facing errors."""


class InvalidInputError(InvoiceError):
    """The input file is missing, unreadable, or an unsupported type."""


class ConfigError(InvoiceError):
    """Configuration problem, such as a missing API key."""


class ExtractionError(InvoiceError):
    """The AI service failed or returned unusable output."""