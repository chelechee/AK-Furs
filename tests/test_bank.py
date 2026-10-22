import pytest

from akfurs.bank import build_payments, extract_order_no, find_early_payments, solve_q2
from akfurs.io_loaders import load_dataset
from akfurs.normalize import STATUS_PAID
from akfurs.orders import build_clean_lines

KNOWN = {1, 75, 528, 775, 828, 921}


def test_phone_fragments_are_not_order_numbers():
    assert extract_order_no('Предоплата заказ 775, тел. +7 964 847-86-23', KNOWN) == 775


def test_invoice_number_is_matched():
    assert extract_order_no('по счету №828 от 13.12.2025', KNOWN) == 828


def test_number_outside_crm_is_unidentified():
    assert extract_order_no('Оплата заказа A-01180', KNOWN) is None


def test_purpose_without_number_is_unidentified():
    assert extract_order_no('Оплата по договору', KNOWN) is None


def test_ambiguous_purpose_raises():
    with pytest.raises(ValueError):
        extract_order_no('заказ 75 и 528', KNOWN)


@pytest.fixture(scope='module')
def prepared(data_dir):
    dataset = load_dataset(data_dir)
    lines = build_clean_lines(dataset['pricebook'], dataset['crm'])
    known = {line.order_no for line in lines}
    payments = build_payments(dataset['bank'], known)
    return lines, known, payments


def test_only_inflows_are_loaded(prepared):
    _, _, payments = prepared
    assert len(payments) == 1168


def test_every_inflow_is_classified(prepared):
    _, known, payments = prepared
    for payment in payments:
        assert payment.order_no is None or payment.order_no in known


def test_no_payment_earlier_than_its_order(prepared):
    lines, _, payments = prepared
    assert find_early_payments(lines, payments) == []


def test_q2b_unidentified_count_and_sum(prepared):
    lines, _, payments = prepared
    _, count, total = solve_q2(lines, payments)
    assert count == 16
    assert total > 0
    assert total == total.to_integral_value()


def test_q2a_is_subset_of_paid_orders_and_sorted(prepared):
    lines, _, payments = prepared
    without, _, _ = solve_q2(lines, payments)
    paid = {line.order_no for line in lines if line.status == STATUS_PAID}
    assert set(without) <= paid
    assert without == sorted(without)
    assert len(without) == len(set(without))
