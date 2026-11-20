# Point of sale

Transport, Services, E-Commerce, Retail and Agriculture owners can open **Point of sale** in the workspace sidebar at /pos/. Services businesses also keep the existing bookings platform.

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


## Screenshot imports and resale stock

Open **Import screenshots** at /pos/import/. Upload 1–3 PNG, JPEG or WebP
screenshots from a single checkout, with a combined size up to 3 MB. The decoder
checks file content, rejects animated/oversized images (16 megapixels per image),
strips metadata and bounds the provider payload. Images are sent to Groq only
after explicit owner consent and are not saved by 4Tax. Crop out personal and
payment details before upload.

The vision model extracts up to 30 item rows with variants, quantities and
reference purchase prices/currencies. Review every row, remove duplicates and
match existing stock when appropriate. Unclear quantities require correction.
Purchase prices are not converted to Maloti or treated as selling prices.
Confirm that goods have arrived before adding their quantities. Pending imports
can be revisited from the upload page.

The StockImport table stores extracted text and the reviewed application result,
not the images. A per-business digest detects repeated identical screenshot
batches; cropped or overlapping images still require manual duplicate review.
Atomic business-row locking makes repeated confirmations safe. Existing products
retain their names/prices/VAT; new items start at zero catalogue price and the
business's configured VAT rate. Record purchase expenses separately.

Open **Stock table & resale** at /pos/inventory/ to search all stock-tracked items,
including inactive/sold-out items, 25 per page. Tick available items on one page,
enter quantities and per-unit selling prices before VAT, choose the payment
account, and confirm payment received. Prices apply only to that sale. Stock
decrements, a receipt is created and balanced ledger entries post atomically.
Retry protection includes the entered prices, and concurrent sales cannot
oversell. Use the normal receipt refund flow for returns.

Configuration: GROQ_API_KEY (existing bookkeeping key) and optional
GROQ_STOCK_VISION_MODEL (default qwen/qwen3.8-27b). Recommendations retain their
separate key. Pillow validates and normalises screenshots.

Deployment requires applying pos.0002_stockimport with production approval before
merging. No existing financial data is rewritten. Automated tests mock provider
calls; PostgreSQL CI covers concurrent confirmation and last-item resale.
Groq vision reference: https://console.groq.com/docs/vision
