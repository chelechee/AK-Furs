import pytest

from akfurs.bank import build_payments, extract_order_no, find_early_payments, solve_q2
from akfurs.io_loaders import load_dataset
from akfurs.normalize import STATUS_PAID
from akfurs.orders import build_clean_lines

KNOWN = {1, 75, 528, 775, 828, 921}


def test_phone_fragments_are_not_order_numbers():
    assert extract_order_no('Предоплата заказ 775, тел. +7 964 847-86-23', KNOWN) == 775


def test_invoice_reference_maps_to_order_number_under_documented_source_convention():
    assert extract_order_no('по счету №828 от 13.12.2025', KNOWN) == 828


def test_conflicting_order_and_invoice_references_are_rejected():
    with pytest.raises(ValueError, match='ambiguous order reference'):
        extract_order_no('оплата заказа 75 по счету №828', KNOWN)


def test_contract_number_is_not_assumed_to_be_an_order():
    assert extract_order_no('оплата по договору №75', KNOWN) is None
    assert extract_order_no('оплата по договору A-75', KNOWN) is None
    assert extract_order_no('перевод, референс №75', KNOWN) is None


def test_explicit_order_survives_another_contract_reference():
    assert extract_order_no('оплата заказа 75 по договору A-828', KNOWN) == 75


def test_number_outside_crm_is_unidentified():
    assert extract_order_no('Оплата заказа A-01180', KNOWN) is None


def test_purpose_without_number_is_unidentified():
    assert extract_order_no('Оплата по договору', KNOWN) is None


def test_ambiguous_purpose_raises():
    with pytest.raises(ValueError):
        extract_order_no('заказ 75 и 528', KNOWN)


def test_amount_matching_another_order_is_not_an_order_reference():
    assert extract_order_no('Оплата заказа A-75, сумма 1000 руб.', {75, 1000}) == 75


def test_numbered_invoice_reference_is_not_overridden_by_amount():
    assert extract_order_no('По счету №828, сумма 1000 ₽', {828, 1000}) == 828


def test_phone_in_eight_format_is_removed_before_number_matching():
    purpose = 'Оплата заказа 75, телефон 8 (495) 123-45-67'
    assert extract_order_no(purpose, {8, 45, 67, 75, 123, 495}) == 75


def test_date_components_are_not_order_references():
    assert extract_order_no('Оплата заказа 75 от 13/12/2025', KNOWN) == 75


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
