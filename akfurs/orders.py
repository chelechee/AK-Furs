from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from .normalize import (
    build_article_map,
    build_manager_map,
    normalize_person,
    normalize_status,
    order_no,
    parse_date,
    parse_datetime,
    parse_money,
    unit_price_after_discount,
)


@dataclass(frozen=True)
class OrderLine:
    order_no: int
    line_no: int
    created: date
    client: str
    manager: str
    source: str
    article: str
    qty: int
    price: Decimal
    discount_raw: str
    unit_after: Decimal
    status: str
    comment: str
    uploaded: datetime
    row_index: int


def build_lines(records, manager_map, article_map):
    lines = []
    for index, row in enumerate(records):
        manager_raw = row['Менеджер']
        manager = manager_map.get(normalize_person(manager_raw))
        if manager is None:
            raise ValueError('unknown manager: {!r}'.format(manager_raw))

        article_raw = row['Артикул'].strip()
        article = article_map.get(article_raw, article_raw)

        price = parse_money(row['Цена за ед.'])
        qty = int(str(row['Кол-во']).strip())
        discount_raw = row['Скидка'].strip()

        lines.append(OrderLine(
            order_no=order_no(row['Номер заказа']),
            line_no=int(str(row['№ строки']).strip()),
            created=parse_date(row['Дата создания']),
            client=row['Клиент'].strip(),
            manager=manager,
            source=row['Источник'].strip(),
            article=article,
            qty=qty,
            price=price,
            discount_raw=discount_raw,
            unit_after=unit_price_after_discount(price, qty, discount_raw),
            status=normalize_status(row['Статус']),
            comment=row['Комментарий'].strip(),
            uploaded=parse_datetime(row['Выгружено']),
            row_index=index,
        ))
    return lines


def dedupe(lines):
    best = {}
    for line in lines:
        key = (line.order_no, line.line_no)
        current = best.get(key)
        if current is None or (line.uploaded, line.row_index) > (current.uploaded, current.row_index):
            best[key] = line
    return sorted(best.values(), key=lambda line: (line.order_no, line.line_no))


def summarise(lines):
    return len({line.order_no for line in lines}), len(lines)


def build_clean_lines(pricebook, crm_records):
    manager_map = build_manager_map(
        [(entry['canonical'], entry['variants']) for entry in pricebook['managers']])
    article_map = build_article_map(
        [(entry['old'], entry['new']) for entry in pricebook['renames']])
    return dedupe(build_lines(crm_records, manager_map, article_map))
