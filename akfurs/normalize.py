import re
from datetime import date, datetime, timedelta
from decimal import Decimal

EXCEL_EPOCH = date(1899, 12, 30)

MONTHS = {
    'янв': 1, 'фев': 2, 'мар': 3, 'апр': 4, 'май': 5, 'мая': 5, 'июн': 6,
    'июл': 7, 'авг': 8, 'сен': 9, 'окт': 10, 'ноя': 11, 'дек': 12,
}

STATUS_PAID = 'Оплачен'
STATUS_CANCELLED = 'Отменён'
STATUS_REFUND = 'Возврат'
STATUS_IN_PROGRESS = 'В работе'

_STATUS_ALIASES = {
    'paid': STATUS_PAID,
    'оплачено': STATUS_PAID,
    'оплачен': STATUS_PAID,
    'cancelled': STATUS_CANCELLED,
    'отменен': STATUS_CANCELLED,
    'refund': STATUS_REFUND,
    'возврат': STATUS_REFUND,
}


def order_no(value):
    digits = re.sub(r'\D', '', str(value))
    if not digits:
        raise ValueError('order number without digits: {!r}'.format(value))
    return int(digits)


def parse_date(value):
    v = str(value).strip()
    if not v:
        raise ValueError('empty date')

    v = re.sub(r'[T ]\d{1,2}:\d{2}(:\d{2})?(\.\d+)?$', '', v).strip()

    m = re.fullmatch(r'(\d{4})-(\d{1,2})-(\d{1,2})', v)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    m = re.fullmatch(r'(\d{4})/(\d{1,2})/(\d{1,2})', v)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    m = re.fullmatch(r'(\d{1,2})\.(\d{1,2})\.(\d{4})', v)
    if m:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))

    m = re.fullmatch(r'(\d{1,2})[-/](\d{1,2})[-/](\d{4})', v)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if day > 12 and month > 12:
            raise ValueError('both parts of the date exceed 12: {!r}'.format(value))
        if month > 12:
            day, month = month, day
        return date(year, month, day)

    m = re.fullmatch(r'(\d{1,2})\s+([А-Яа-яЁё]+)\.?\s+(\d{4})', v)
    if m:
        prefix = m.group(2).lower()[:3]
        if prefix not in MONTHS:
            raise ValueError('unknown month name in {!r}'.format(value))
        return date(int(m.group(3)), MONTHS[prefix], int(m.group(1)))

    if re.fullmatch(r'\d{5}', v):
        return EXCEL_EPOCH + timedelta(days=int(v))

    raise ValueError('unknown date format: {!r}'.format(value))


_SPACE_TRANSLATION = {
    '\u00a0': ' ',
    '\u202f': ' ',
    '\u2009': ' ',
    '\u2007': ' ',
    '\u200b': '',
}


def parse_datetime(value):
    v = str(value).strip()
    if not v:
        raise ValueError('empty datetime')
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%dT%H:%M:%S',
                '%Y-%m-%dT%H:%M', '%d.%m.%Y %H:%M:%S', '%d.%m.%Y %H:%M'):
        try:
            return datetime.strptime(v, fmt)
        except ValueError:
            continue
    raise ValueError('unknown datetime format: {!r}'.format(value))


def parse_money(value):
    raw = str(value)
    for source, target in _SPACE_TRANSLATION.items():
        raw = raw.replace(source, target)
    raw = raw.strip()
    if not raw:
        raise ValueError('empty money value')

    v = raw.lower()
    for token in ('руб.', 'рублей', 'рубля', 'руб', '₽', 'р.'):
        v = v.replace(token, '')
    v = v.strip().rstrip('.').strip()

    multiplier = Decimal(1)
    if v.endswith('млн'):
        multiplier = Decimal(1_000_000)
        v = v[:-3].strip().rstrip('.').strip()
    elif v.endswith('тыс'):
        multiplier = Decimal(1_000)
        v = v[:-3].strip().rstrip('.').strip()

    if ',' in v and '.' in v:
        if v.rfind(',') > v.rfind('.'):
            v = v.replace('.', '').replace(',', '.')
        else:
            v = v.replace(',', '')
        number = Decimal(v.replace(' ', ''))
    elif re.fullmatch(r'\d{1,3}( \d{3})+(,\d{1,2})?', v):
        number = Decimal(v.replace(' ', '').replace(',', '.'))
    elif re.fullmatch(r'\d{1,3}(,\d{3})+', v):
        number = Decimal(v.replace(',', ''))
    elif re.fullmatch(r'\d+,\d{1,2}', v):
        number = Decimal(v.replace(',', '.'))
    elif re.fullmatch(r'\d+(\.\d+)?', v):
        number = Decimal(v)
    else:
        raise ValueError('unknown money format: {!r}'.format(value))

    return number * multiplier


def parse_discount(value):
    raw = str(value).strip()
    if not raw:
        return None, Decimal(0)
    if raw.endswith('%'):
        percent = Decimal(raw[:-1].replace(',', '.').strip())
        return 'percent', percent
    return 'absolute', parse_money(raw)


def unit_price_after_discount(price, qty, discount_raw):
    kind, amount = parse_discount(discount_raw)
    if kind is None:
        return price
    if kind == 'percent':
        return price * (Decimal(1) - amount / Decimal(100))
    return (price * Decimal(qty) - amount) / Decimal(qty)


def normalize_status(value):
    v = ' '.join(str(value).split()).lower().replace('ё', 'е')
    return _STATUS_ALIASES.get(v, STATUS_IN_PROGRESS)


def normalize_person(value):
    return ' '.join(str(value).split()).lower().replace('ё', 'е')


def build_manager_map(manager_rows):
    mapping = {}
    for row in manager_rows:
        canonical = str(row[0]).strip()
        for variant in str(row[1]).split('|'):
            mapping[normalize_person(variant)] = canonical
    return mapping


def build_article_map(rename_rows):
    return {str(row[0]).strip(): str(row[1]).strip() for row in rename_rows if row[0]}
