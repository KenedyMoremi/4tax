"""Build an allowlisted aggregate snapshot; never send personal or transaction text."""
from datetime import timedelta
from django.db.models import Count
from django.utils import timezone
from bookkeeping.models import JournalEntry
from bookkeeping.reporting import financial_report
from business_profiles.models import SectorProfile
from bookings.models import Appointment
from pos.models import Product


def snapshot(business):
    end = timezone.localdate()
    start = end - timedelta(days=29)
    previous_start = start - timedelta(days=30)
    current = financial_report(business, start, end)
    previous = financial_report(business, previous_start, start - timedelta(days=1))
    sector = SectorProfile.objects.filter(business=business).values_list('sector', flat=True).first() or 'unspecified'
    metrics = {}
    def add(key, label, value, unit='LSL'):
        metrics[key] = {'label': label, 'value': str(value), 'unit': unit}
    for key, label in [('income', 'Recorded revenue'), ('expenses', 'Recorded expenses'), ('profit', 'Recorded surplus / deficit')]:
        add(key, label + ' · last 30 days', current[key])
        add('previous_' + key, label + ' · previous 30 days', previous[key])
    rows = current['balance_rows']
    add('cash_balance', 'Cash, bank and mobile-money balance · today', sum(r['net'] for r in rows if r['account'].is_cash))
    add('receivable', 'Accounts receivable balance · today', sum(r['net'] for r in rows if r['account'].code == '1100'))
    add('payable', 'Accounts payable balance · today', -sum(r['net'] for r in rows if r['account'].code == '2000'))
    entries = JournalEntry.objects.filter(business=business, date__range=(start, end)).count()
    add('entries', 'Posted journal entries · last 30 days', entries, 'count')
    if sector == 'services':
        counts = dict(Appointment.objects.filter(business=business, starts_at__date__range=(start, end)).values('status').annotate(n=Count('pk')).values_list('status', 'n'))
        for status in ['completed', 'cancelled', 'no_show']:
            add('bookings_' + status, status.replace('_', ' ').capitalize() + ' appointments · last 30 days', counts.get(status, 0), 'count')
    elif sector in ['transport', 'ecommerce', 'retail', 'agriculture']:
        products = Product.objects.filter(business=business, active=True, track_stock=True)
        add('tracked_products', 'Active stock-tracked items · today', products.count(), 'count')
        add('out_of_stock', 'Out-of-stock active items · today', products.filter(stock=0).count(), 'count')
    return {
        'sector': sector, 'currency': 'LSL', 'period': {'start': str(start), 'end': str(end)},
        'previous_period': {'start': str(previous_start), 'end': str(start - timedelta(days=1))},
        'metrics': metrics,
        'limitations': [
            'Recorded activity may be incomplete; no market data or customer demand estimates are available.',
            'Recorded surplus is revenue minus recorded expenses, not a forecast or inventory-adjusted profit.',
            'Account balances depend on opening balances and reconciled records.',
            'Booking counts do not represent money received. Stock counts do not measure inventory value.',
        ],
    }
