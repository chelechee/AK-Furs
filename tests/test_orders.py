from datetime import date, datetime
from decimal import Decimal

from akfurs.io_loaders import read_crm, read_pricebook
from akfurs.normalize import STATUS_IN_PROGRESS, STATUS_PAID, build_manager_map
from akfurs.orders import build_clean_lines, build_lines, dedupe, summarise

MANAGERS = {'вероника белова': 'Вероника Белова'}
ARTICLES = {'OLD-01': 'NEW-01'}


def record(**overrides):
    base = {
        'Номер заказа': 'A-00001',
        '№ строки': '1',
        'Дата создания': '2025-03-03',
        'Клиент': 'CL-00001',
        'Менеджер': 'Вероника Белова',
        'Источник': 'Сайт',
        'Артикул': 'SOB-SH-01',
        'Кол-во': '1',
        'Цена за ед.': '50000',
        'Валюта': 'RUB',
        'Скидка': '',
        'Статус': 'Оплачен',
        'Комментарий': '',
        'Выгружено': '2026-10-01 09:00',
    }
    base.update(overrides)
    return base


def test_build_lines_normalizes_fields():
    lines = build_lines([record()], MANAGERS, ARTICLES)
    line = lines[0]
    assert line.order_no == 1
    assert line.manager == 'Вероника Белова'
    assert line.created == date(2025, 3, 3)
    assert line.price == Decimal('50000')
    assert line.unit_after == Decimal('50000')
    assert line.status == STATUS_PAID
    assert line.uploaded == datetime(2026, 10, 1, 9, 0)


def test_build_lines_applies_renames_and_discount():
    lines = build_lines([record(**{'Артикул': 'OLD-01', 'Скидка': '10%', 'Статус': 'NEW'})],
                        MANAGERS, ARTICLES)
    assert lines[0].article == 'NEW-01'
    assert lines[0].unit_after == Decimal('45000')
    assert lines[0].status == STATUS_IN_PROGRESS


def test_dedupe_keeps_latest_upload():
    rows = [
        record(**{'Статус': 'NEW', 'Выгружено': '2026-09-30 12:00'}),
        record(**{'Статус': 'Оплачен', 'Выгружено': '2026-10-01 09:00'}),
    ]
    lines = dedupe(build_lines(rows, MANAGERS, ARTICLES))
    assert len(lines) == 1
    assert lines[0].status == STATUS_PAID


def test_dedupe_accepts_identical_latest_timestamp_independent_of_order():
    same_time = '2026-10-01 09:00'
    rows = [
        record(**{'Выгружено': same_time}),
        record(**{'Выгружено': same_time}),
    ]
    first = dedupe(build_lines(rows, MANAGERS, ARTICLES))
    second = dedupe(build_lines(list(reversed(rows)), MANAGERS, ARTICLES))
    assert len(first) == 1 and len(second) == 1
    assert first[0].status == second[0].status == STATUS_PAID


def test_dedupe_rejects_conflicting_latest_timestamp():
    same_time = '2026-10-01 09:00'
    rows = [
        record(**{'Статус': 'NEW', 'Выгружено': same_time}),
        record(**{'Статус': 'Оплачен', 'Выгружено': same_time}),
    ]
    import pytest
    with pytest.raises(ValueError, match='same latest upload time'):
        dedupe(build_lines(rows, MANAGERS, ARTICLES))


def test_dedupe_keeps_different_line_numbers():
    rows = [
        record(**{'№ строки': '1'}),
        record(**{'№ строки': '2'}),
    ]
    lines = dedupe(build_lines(rows, MANAGERS, ARTICLES))
    assert len(lines) == 2
    assert summarise(lines) == (1, 2)


def test_summarise_counts_orders_and_lines():
    rows = [
        record(**{'Номер заказа': 'A-1', '№ строки': '1'}),
        record(**{'Номер заказа': 'A-1', '№ строки': '2'}),
        record(**{'Номер заказа': 'А-00002', '№ строки': '1'}),
    ]
    assert summarise(dedupe(build_lines(rows, MANAGERS, ARTICLES))) == (2, 3)


def test_unknown_manager_fails_loudly():
    try:
        build_lines([record(**{'Менеджер': 'Неизвестный Кто-то'})], MANAGERS, ARTICLES)
    except ValueError as error:
        assert 'unknown manager' in str(error)
    else:
        raise AssertionError('unknown manager must raise')


def test_q1_on_real_data(data_dir):
    crm = read_crm(data_dir / '01_crm_orders_export.csv')
    pricebook = read_pricebook(data_dir / '03_catalog_prices_reference.xlsx')
    lines = build_clean_lines(pricebook, crm)
    assert summarise(lines) == (1000, 1368)
    assert min(line.order_no for line in lines) == 1
    assert max(line.order_no for line in lines) == 1000


def test_real_manager_map_covers_every_row(data_dir):
    crm = read_crm(data_dir / '01_crm_orders_export.csv')
    pricebook = read_pricebook(data_dir / '03_catalog_prices_reference.xlsx')
    mapping = build_manager_map(
        [(entry['canonical'], entry['variants']) for entry in pricebook['managers']])
    from akfurs.normalize import normalize_person

    unknown = {row['Менеджер'] for row in crm
               if normalize_person(row['Менеджер']) not in mapping}
    assert unknown == set()
