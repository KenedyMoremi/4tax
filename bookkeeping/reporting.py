from decimal import Decimal
from django.db.models import Sum, Q
from .models import Account, JournalLine, ZERO, money

def account_balances(business, end, start=None):
    condition = Q(journalline__entry__date__lte=end)
    if start:
        condition &= Q(journalline__entry__date__gte=start)
    accounts = Account.objects.filter(business=business).annotate(debits=Sum('journalline__debit', filter=condition, default=ZERO), credits=Sum('journalline__credit', filter=condition, default=ZERO))
    rows = []
    for a in accounts:
        net = money(a.debits - a.credits)
        normal = net if a.kind in ['asset','expense'] else -net
        rows.append({'account':a, 'debits':money(a.debits), 'credits':money(a.credits), 'net':net, 'balance':normal, 'trial_debit':max(net,ZERO), 'trial_credit':max(-net,ZERO)})
    return rows

def financial_report(business, start, end):
    period = account_balances(business, end, start)
    balances = account_balances(business, end)
    income = sum((r['balance'] for r in period if r['account'].kind == 'income'), ZERO)
    expenses = sum((r['balance'] for r in period if r['account'].kind == 'expense'), ZERO)
    assets = sum((r['balance'] for r in balances if r['account'].kind == 'asset'), ZERO)
    liabilities = sum((r['balance'] for r in balances if r['account'].kind == 'liability'), ZERO)
    equity = sum((r['balance'] for r in balances if r['account'].kind == 'equity'), ZERO)
    retained = sum((r['balance'] for r in balances if r['account'].kind == 'income'), ZERO) - sum((r['balance'] for r in balances if r['account'].kind == 'expense'), ZERO)
    vat_in = next(r['net'] for r in period if r['account'].code == '1200')
    vat_out = -next(r['net'] for r in period if r['account'].code == '2100')
    return {'period_rows':period, 'balance_rows':balances, 'income':income, 'expenses':expenses, 'profit':income-expenses, 'assets':assets, 'liabilities':liabilities, 'equity':equity, 'retained':retained, 'total_equity':equity+retained, 'liabilities_equity':liabilities+equity+retained, 'balance_difference':assets-liabilities-equity-retained, 'vat_in':vat_in, 'vat_out':vat_out, 'vat_net':vat_out-vat_in, 'trial_debits':sum((r['trial_debit'] for r in balances), ZERO), 'trial_credits':sum((r['trial_credit'] for r in balances), ZERO)}
