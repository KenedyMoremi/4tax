# Point of sale

Transport, E-Commerce, Retail and Agriculture owners can open **Point of sale** in the workspace sidebar at /pos/. Services businesses use the existing bookings platform.

1. Add catalogue items with a price before VAT and a unit (each, kg, passenger or trip). VAT requires a VAT-registered business. An optional unique SKU helps search.
2. Enable stock tracking for physical goods and use **Stock** to add opening quantities. Adjustments require a reason and retain an audit history.
3. Add items to the basket, enter quantities, select cash, bank, M-Pesa or EcoCash, and confirm the payment has already been received.
4. Complete the sale and print its private receipt. Sales and VAT automatically appear in bookkeeping reports.
5. Open a receipt to record a full refund after returning the customer's money. Choose whether returned goods should go back into stock.

Cash can include change; bank/mobile money must match the sale total. This records external payments; it does not charge a card or initiate a mobile-money transfer. Stock tracks quantities, not inventory valuation or cost of goods sold. Record purchases through the existing bookkeeping expense workflow. Partial refunds, split tender, offline checkout and separate cashier accounts are not included.

## Integrity and access

Only the business owner can access its catalogue, sales, stock and receipts. Prices and VAT are calculated on the server with decimal rounding per line. Transactions lock the business row on PostgreSQL, update stock and post a balanced journal together. Request tokens prevent duplicate sales and stock adjustments. A sale can be refunded only once, using a reversing journal; original receipts retain the business and item details at checkout.

The browser keeps the current basket and retry token in session storage, scoped to the business. Customer and payment details are not saved there. JavaScript is required for the checkout basket. A price change requires removing and re-adding the affected item before payment can be recorded.

## Deployment and validation

Apply pos.0001_initial before deploying code that enables the POS. It creates new tables and constraints without modifying existing financial records. Production migrations require confirmation under AGENTS.md. No additional environment variables or external services are required.

Run:

    python manage.py test pos
    python manage.py makemigrations --check --dry-run --settings=config.test_settings

The PostgreSQL CI job runs POS tests and concurrent last-stock, duplicate checkout and refund tests against a disposable database. They are skipped in the default SQLite suite.
