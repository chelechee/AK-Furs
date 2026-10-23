from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from .normalize import STATUS_CANCELLED


@dataclass(frozen=True)
class PricePeriod:
    article: str
    valid_from: object
    valid_to: object
    recommended: Decimal
    minimum: Decimal


def as_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    return value


def build_history(history_rows):
    periods = {}
    for row in history_rows:
        valid_from = as_date(row['valid_from'])
        valid_to = as_date(row['valid_to'])
        if valid_from is None:
            raise ValueError('price period for {!r} has no start date'.format(row['article']))
        if valid_to is not None and valid_to < valid_from:
            raise ValueError('price period for {!r} ends before it starts'.format(row['article']))
        periods.setdefault(row['article'], []).append(PricePeriod(
            article=row['article'],
            valid_from=valid_from,
            valid_to=valid_to,
            recommended=Decimal(str(row['recommended'])),
            minimum=Decimal(str(row['minimum'])),
        ))
    for items in periods.values():
        items.sort(key=lambda period: period.valid_from)
        for previous, current in zip(items, items[1:]):
            if previous.valid_to is None or current.valid_from <= previous.valid_to:
                raise ValueError('overlapping price periods for {!r}'.format(current.article))
    return periods


def minimum_price(periods, article, on_date):
    for period in periods.get(article, []):
        if period.valid_from <= on_date and (period.valid_to is None or on_date <= period.valid_to):
            return period.minimum
    raise ValueError('no price period for {!r} on {}'.format(article, on_date))


def solve_q3(lines, periods):
    violations = []
    for line in lines:
        if line.status == STATUS_CANCELLED:
            continue
        minimum = minimum_price(periods, line.article, line.created)
        if line.unit_after < minimum:
            violations.append(line)

    by_manager = {}
    for line in violations:
        by_manager[line.manager] = by_manager.get(line.manager, 0) + 1
    return len(violations), dict(sorted(by_manager.items()))
