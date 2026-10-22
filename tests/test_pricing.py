from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from akfurs.io_loaders import load_dataset
from akfurs.normalize import STATUS_CANCELLED, STATUS_PAID
from akfurs.orders import build_clean_lines
from akfurs.pricing import build_history, minimum_price, solve_q3


@pytest.fixture(scope='module')
def prepared(data_dir):
    dataset = load_dataset(data_dir)
    periods = build_history(dataset['pricebook']['history'])
    lines = build_clean_lines(dataset['pricebook'], dataset['crm'])
    return periods, lines


def test_period_boundaries(prepared):
    periods, _ = prepared
    assert minimum_price(periods, 'CHN-PAL-01', date(2025, 6, 30)) == Decimal('60000')
    assert minimum_price(periods, 'CHN-PAL-01', date(2025, 7, 1)) == Decimal('62000')
    assert minimum_price(periods, 'CHN-PAL-01', date(2026, 7, 1)) == Decimal('69000')


def test_last_period_is_open_ended(prepared):
    periods, _ = prepared
    assert minimum_price(periods, 'CHN-PAL-01', date(2027, 1, 1)) == Decimal('69000')


def test_missing_period_raises(prepared):
    periods, _ = prepared
    with pytest.raises(ValueError):
        minimum_price(periods, 'UNKNOWN-01', date(2025, 5, 5))


def test_cancelled_lines_are_ignored(prepared):
    periods, _ = prepared
    line = SimpleNamespace(article='CHN-PAL-01', created=date(2025, 5, 5),
                           status=STATUS_CANCELLED, unit_after=Decimal('1'), manager='X')
    assert solve_q3([line], periods) == (0, {})


def test_violation_is_detected_and_grouped(prepared):
    periods, _ = prepared
    cheap = SimpleNamespace(article='CHN-PAL-01', created=date(2025, 5, 5),
                            status=STATUS_PAID, unit_after=Decimal('50000'), manager='A')
    fine = SimpleNamespace(article='CHN-PAL-01', created=date(2025, 5, 5),
                           status=STATUS_PAID, unit_after=Decimal('60000'), manager='B')
    assert solve_q3([cheap, fine], periods) == (1, {'A': 1})


def test_every_line_resolves_to_a_period(prepared):
    periods, lines = prepared
    for line in lines:
        minimum_price(periods, line.article, line.created)


def test_manager_breakdown_sums_to_total(prepared):
    periods, lines = prepared
    total, by_manager = solve_q3(lines, periods)
    assert sum(by_manager.values()) == total
    assert 0 <= total <= len(lines)


def test_breakdown_uses_canonical_names(prepared):
    periods, lines = prepared
    _, by_manager = solve_q3(lines, periods)
    assert set(by_manager) <= {line.manager for line in lines}
