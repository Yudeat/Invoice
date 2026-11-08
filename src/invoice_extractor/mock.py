from .models import RawInvoice, RawLineItem


def mock_raw_invoice() -> RawInvoice:
    return RawInvoice(
        invoice_number="RT-2024-1052",
        invoice_date="2024-10-14",
        due_date="2024-11-13",
        supplier_name="RiverTech Supplies Ltd.",
        customer_name="Deutschelink GmbH",
        currency="NPR",
        items=[
            RawLineItem(description="HDPE Pipe 110mm (6m length)", quantity=50, unit="pcs", unit_price=1250.00, line_total=62500.00),
            RawLineItem(description="HDPE Elbow 90\u00b0 110mm", quantity=20, unit="pcs", unit_price=450.00, line_total=9000.00),
            RawLineItem(description="HDPE Coupling 110mm", quantity=30, unit="pcs", unit_price=300.00, line_total=9000.00),
            RawLineItem(description="Welding Service", quantity=10, unit="hrs", unit_price=1500.00, line_total=15000.00),
            RawLineItem(description="Delivery Charge", quantity=1, unit="lot", unit_price=5000.00, line_total=5000.00),
        ],
        subtotal=100500.00,
        tax_rate_percent=13,
        tax_amount=13065.00,
        total_amount=113565.00,
    )
