import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .normalize import STATUS_PAID, parse_date, parse_money

_DATE_RE = re.compile(r'\b\d{2}\.\d{2}\.\d{4}\b')
_PHONE_RE = re.compile(r'\+?7[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}')
_LONG_DIGITS_RE = re.compile(r'\d{10,}')
_DIGITS_RE = re.compile(r'\d+')

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
    candidates = {int(token) for token in _DIGITS_RE.findall(text)}
    matched = sorted(candidate for candidate in candidates if candidate in known_orders)
    if len(matched) > 1:
        raise ValueError('ambiguous order reference in {!r}: {}'.format(purpose, matched))
    return matched[0] if matched else None


def build_payments(records, known_orders):
    payments = []
    for row in records:
        if row['kind'] != INFLOW:
            continue
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
