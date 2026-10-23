from datetime import date
from decimal import Decimal

import pytest

from akfurs.normalize import (
    STATUS_CANCELLED,
    STATUS_IN_PROGRESS,
    STATUS_PAID,
    STATUS_REFUND,
    build_manager_map,
    build_article_map,
    normalize_person,
    normalize_status,
    order_no,
    parse_date,
    parse_money,
    unit_price_after_discount,
)


def test_order_no_collapses_all_spellings():
    for raw in ('A-00075', 'А-75', 'a-75', 'A75', ' a-372', 'A-00922',
                'A–75', 'A 75', '№ 00075', 'заказ 75'):
        assert isinstance(order_no(raw), int)
    assert {order_no(x) for x in ('A-00075', 'А-75', 'a-75', 'A75')} == {75}


def test_order_no_rejects_values_without_digits():
    with pytest.raises(ValueError):
        order_no('без номера')


def test_order_no_rejects_unrecognized_composite_identifiers():
    with pytest.raises(ValueError):
        order_no('A-75/1')


@pytest.mark.parametrize('raw,expected', [
    ('2025-03-03', date(2025, 3, 3)),
    ('17.03.2025', date(2025, 3, 17)),
    ('31/07/2025', date(2025, 7, 31)),
    ('11/02/2025', date(2025, 2, 11)),
    ('21 июн 2026', date(2026, 6, 21)),
    ('24 мая 2026', date(2026, 5, 24)),
    ('45752', date(2025, 4, 5)),
])
def test_parse_date_formats(raw, expected):
    assert parse_date(raw) == expected


def test_parse_date_swaps_month_when_first_part_exceeds_twelve():
    assert parse_date('07/30/2025') == date(2025, 7, 30)


def test_parse_date_rejects_unknown_format():
    with pytest.raises(ValueError):
        parse_date('вчера')


@pytest.mark.parametrize('raw,expected', [
    ('50 000', Decimal('50000')),
    ('17000', Decimal('17000')),
    ('52000,00', Decimal('52000')),
    ('17,000.00', Decimal('17000')),
    ('2 200 000', Decimal('2200000')),
    ('74 000', Decimal('74000')),
    ('2,48 млн', Decimal('2480000')),
    ('158 тыс.', Decimal('158000')),
    ('1,600.00', Decimal('1600')),
])
def test_parse_money_formats(raw, expected):
    assert parse_money(raw) == expected


def test_parse_money_does_not_confuse_separators():
    assert parse_money('17,000.00') == Decimal('17000')
    assert parse_money('52000,00') == Decimal('52000')
    assert parse_money('17,000.00') != Decimal('17')


def test_parse_money_rejects_garbage():
    with pytest.raises(ValueError):
        parse_money('дорого')


def test_percent_discount_applies_to_unit_price():
    result = unit_price_after_discount(Decimal('159000'), 1, '7%')
    assert result == Decimal('159000') * (Decimal(1) - Decimal('0.07'))


def test_absolute_discount_is_spread_over_quantity():
    result = unit_price_after_discount(Decimal('50000'), 2, '2 100')
    assert result == (Decimal('100000') - Decimal('2100')) / 2


def test_discount_allows_space_before_percent_sign():
    assert unit_price_after_discount(Decimal('100000'), 1, '10 %') == Decimal('90000')


@pytest.mark.parametrize('discount', ['-1%', '101%', '-1', '100001'])
def test_discount_rejects_out_of_range_values(discount):
    with pytest.raises(ValueError):
        unit_price_after_discount(Decimal('100000'), 1, discount)


def test_discount_rejects_zero_quantity():
    with pytest.raises(ValueError, match='quantity must be positive'):
        unit_price_after_discount(Decimal('100000'), 0, '10%')


def test_empty_discount_keeps_price():
    assert unit_price_after_discount(Decimal('50000'), 1, '') == Decimal('50000')


@pytest.mark.parametrize('raw,expected', [
    ('PAID', STATUS_PAID),
    ('оплачено', STATUS_PAID),
    ('Оплачен', STATUS_PAID),
    ('Оплачен ', STATUS_PAID),
    ('CANCELLED', STATUS_CANCELLED),
    ('Отменён', STATUS_CANCELLED),
    ('отменен', STATUS_CANCELLED),
    ('REFUND', STATUS_REFUND),
    ('Возврат', STATUS_REFUND),
    ('возврат', STATUS_REFUND),
    ('NEW', STATUS_IN_PROGRESS),
    ('Ждём оплату', STATUS_IN_PROGRESS),
    ('в работе', STATUS_IN_PROGRESS),
    ('В работе', STATUS_IN_PROGRESS),
])
def test_status_mapping(raw, expected):
    assert normalize_status(raw) == expected


def test_manager_map_ignores_case_and_spaces():
    rows = [
        ('Вероника Белова', 'Вероника Белова | Белова В. | вероника | Veronika B | В. Белова'),
        ('Полина Орлова', 'Полина Орлова | Орлова П. | Полина | P. Orlova | полина орлова '),
    ]
    mapping = build_manager_map(rows)
    assert mapping[normalize_person(' В. Белова')] == 'Вероника Белова'
    assert mapping[normalize_person('полина орлова ')] == 'Полина Орлова'
    assert mapping[normalize_person('ВЕРОНИКА')] == 'Вероника Белова'


def test_manager_map_rejects_alias_collisions():
    with pytest.raises(ValueError, match='maps to both'):
        build_manager_map([
            ('Менеджер Один', 'Ирина'),
            ('Менеджер Два', 'Ирина'),
        ])


def test_article_renames_resolve_chains_and_reject_cycles():
    assert build_article_map([('OLD', 'MID'), ('MID', 'NEW')]) == {
        'OLD': 'NEW', 'MID': 'NEW'
    }
    with pytest.raises(ValueError, match='cycle'):
        build_article_map([('A', 'B'), ('B', 'A')])
