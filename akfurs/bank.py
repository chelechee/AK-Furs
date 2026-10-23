import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .normalize import STATUS_PAID, parse_date, parse_money

_DATE_RE = re.compile(
    r'\b(?:\d{1,2}[./-]\d{1,2}[./-]\d{4}|\d{4}[-/]\d{1,2}[-/]\d{1,2})\b'
)
_PHONE_RE = re.compile(
    r'(?<!\d)(?:\+?7|8)[\s().-]*\d{3}[\s().-]*\d{3}[\s.-]*\d{2}[\s.-]*\d{2}(?!\d)'
)
_LONG_DIGITS_RE = re.compile(r'\d{10,}')
_DIGITS_RE = re.compile(r'\d+')
_ORDER_LABEL_RE = re.compile(
    r'\bзаказ(?:а|у|ом)?\s*(?:№\s*)?((?:[aа]\s*[-–—]?\s*)?\d+)', re.IGNORECASE
)
_ORDER_CODE_RE = re.compile(r'(?<!\w)[aа]\s*[-–—]\s*\d+', re.IGNORECASE)
_NUMBERED_REFERENCE_RE = re.compile(r'№\s*\d+')
_INVOICE_REFERENCE_RE = re.compile(
    r'\b(?:номер\s+)?сч[её]т(?:а|у|ом)?(?:-фактур\w*)?\s*'
    r'(?:№\s*|номер\s*)?(\d+)',
    re.IGNORECASE,
)
_DOCUMENT_REFERENCE_RE = re.compile(
    r'\b(?:номер\s+)?(?:договор(?:а|у|ом)?|документ(?:а|у|ом)?|'
    r'акт(?:а|у|ом)?|накладн\w*|'
    r'квитанц\w*|чек|операци\w*|транзакц\w*|референс\w*|'
    r'сертификат\w*|плат[её]жн\w*\s+поручени\w*)\s*'
    r'(?:№\s*|номер\s*)?(?:[aа]\s*[-–—]?\s*)?\d+',
    re.IGNORECASE,
)
_MONEY_RE = re.compile(
    r'(?<!\w)[+-]?\d+(?:[ \u00a0\u202f.,]\d{3})*(?:[,.]\d{1,2})?\s*'
    r'(?:₽|руб(?:\.|ля|лей)?|р\.?|RUB|RUR|тыс\.?|млн\.?)',
    re.IGNORECASE,
)
_LABELED_AMOUNT_RE = re.compile(
    r'\b(?:сумма|суммой|итого|на сумму)\s*[:№]?\s*'
    r'[+-]?\d+(?:[ \u00a0\u202f.,]\d{3})*(?:[,.]\d{1,2})?',
    re.IGNORECASE,
)

INFLOW = 'Поступление'


@dataclass(frozen=True)
class Payment:
    at: date
    amount: Decimal
    counterparty: str
    purpose: str
    order_no: object


def extract_order_no(purpose, known_orders):
    text = _DATE_RE.sub(' ', purpose)
    text = _PHONE_RE.sub(' ', text)
    text = _LONG_DIGITS_RE.sub(' ', text)

    without_amounts = _LABELED_AMOUNT_RE.sub(' ', text)
    without_amounts = _MONEY_RE.sub(' ', without_amounts)
    invoice_references = {int(match.group(1))
                          for match in _INVOICE_REFERENCE_RE.finditer(without_amounts)}
    without_amounts = _INVOICE_REFERENCE_RE.sub(' ', without_amounts)
    without_amounts = _DOCUMENT_REFERENCE_RE.sub(' ', without_amounts)

    order_references = {int(_DIGITS_RE.search(match.group(1)).group())
                        for match in _ORDER_LABEL_RE.finditer(without_amounts)}
    order_references.update(int(_DIGITS_RE.search(match.group()).group())
                            for match in _ORDER_CODE_RE.finditer(without_amounts))
    numbered_references = {int(_DIGITS_RE.search(match.group()).group())
                           for match in _NUMBERED_REFERENCE_RE.finditer(without_amounts)}
    remaining_numbers = {int(token) for token in _DIGITS_RE.findall(without_amounts)}
    if order_references:
        candidates = order_references | invoice_references | numbered_references | remaining_numbers
    elif invoice_references:
        candidates = invoice_references | numbered_references | remaining_numbers
    elif numbered_references:
        candidates = numbered_references | remaining_numbers
    else:
        candidates = remaining_numbers
    matched = sorted(candidate for candidate in candidates if candidate in known_orders)
    if len(matched) > 1:
        raise ValueError('ambiguous order reference in payment purpose; matching orders: {}'.format(
            matched))
    return matched[0] if matched else None


def build_payments(records, known_orders):
    payments = []
    for row in records:
        if row['kind'] != INFLOW:
            continue
        currency = row.get('currency', '').strip().upper()
        if currency and currency not in {'RUR', 'RUB', 'РУБ', '₽'}:
            raise ValueError('unsupported inflow currency: {!r}'.format(currency))
        payments.append(Payment(
            at=parse_date(row['date_raw']),
            amount=parse_money(row['amount_raw']),
            counterparty=row['counterparty'],
            purpose=row['purpose'],
            order_no=extract_order_no(row['purpose'], known_orders),
        ))
    return payments


def solve_q2(lines, payments):
    paid_orders = {line.order_no for line in lines if line.status == STATUS_PAID}
    matched_orders = {payment.order_no for payment in payments if payment.order_no is not None}
    without_payment = sorted(paid_orders - matched_orders)

    unidentified = [payment for payment in payments if payment.order_no is None]
    total = sum((payment.amount for payment in unidentified), Decimal(0))
    return without_payment, len(unidentified), total


def first_created_dates(lines):
    dates = {}
    for line in lines:
        current = dates.get(line.order_no)
        if current is None or line.created < current:
            dates[line.order_no] = line.created
    return dates


def find_early_payments(lines, payments):
    created = first_created_dates(lines)
    return [
        payment for payment in payments
        if payment.order_no in created and payment.at < created[payment.order_no]
    ]
