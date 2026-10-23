import csv
import io
import re
import zipfile
from pathlib import Path

import openpyxl

from .normalize import parse_datetime

CRM_FILENAME = '01_crm_orders_export.csv'
BANK_FILENAME = '02_bank_statement_rub.csv'
PRICEBOOK_FILENAME = '03_catalog_prices_reference.xlsx'
CHATS_FILENAME = '04_client_chats.zip'
DATA_FILES = (CRM_FILENAME, BANK_FILENAME, PRICEBOOK_FILENAME, CHATS_FILENAME)

_MESSAGE_RE = re.compile(
    r'\[(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2}(?::\d{2})?)\]\s*(Клиент|Менеджер)\s*:\s*(.*)'
)

_BANK_COLUMNS = {
    'date_raw': 'Дата операции',
    'time_raw': 'Время',
    'amount_raw': 'Сумма',
    'currency': 'Валюта',
    'kind': 'Тип',
    'counterparty': 'Контрагент',
    'purpose': 'Назначение платежа',
}

_BANK_REQUIRED = ('date_raw', 'amount_raw', 'kind', 'purpose')


def decode_bytes(raw):
    if raw.startswith(b'\xff\xfe') or raw.startswith(b'\xfe\xff'):
        return raw.decode('utf-16')
    try:
        return raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        return raw.decode('cp1251')


def detect_delimiter(text):
    sample = '\n'.join(line for line in text.splitlines()[:5] if line.strip())
    try:
        return csv.Sniffer().sniff(sample, delimiters=';,\t|').delimiter
    except csv.Error:
        return ';'


def read_crm(path):
    text = decode_bytes(Path(path).read_bytes())
    delimiter = detect_delimiter(text)
    with io.StringIO(text) as handle:
        return list(csv.DictReader(handle, delimiter=delimiter))


def read_bank(path):
    text = decode_bytes(Path(path).read_bytes())
    lines = text.splitlines()
    header_index, delimiter = _find_bank_header(lines)
    header = next(csv.reader([lines[header_index]], delimiter=delimiter))
    positions = {name.strip(): index for index, name in enumerate(header) if name.strip()}

    missing = [label for label in _BANK_REQUIRED if _BANK_COLUMNS[label] not in positions]
    if missing:
        raise ValueError('bank header lacks columns: {}'.format(
            ', '.join(_BANK_COLUMNS[label] for label in missing)))

    records = []
    for row in csv.reader(lines[header_index + 1:], delimiter=delimiter):
        if not any(cell.strip() for cell in row):
            continue
        record = {}
        for key, label in _BANK_COLUMNS.items():
            index = positions.get(label)
            record[key] = row[index].strip() if index is not None and index < len(row) else ''
        records.append(record)
    return records


def _find_bank_header(lines):
    for index, line in enumerate(lines):
        if 'Дата операции' in line and 'Назначение платежа' in line:
            return index, detect_delimiter(line)
    raise ValueError('bank header row not found')


def _row_with_cells(worksheet, required):
    for row in worksheet.iter_rows(min_row=1, max_row=15):
        values = {cell.value.strip() for cell in row if isinstance(cell.value, str)}
        if all(item in values for item in required):
            return row[0].row
    raise ValueError('headers {} not found in sheet {!r}'.format(required, worksheet.title))


def _sheet_with_cells(workbook, required):
    for worksheet in workbook.worksheets:
        try:
            return worksheet, _row_with_cells(worksheet, required)
        except ValueError:
            continue
    raise ValueError('no sheet contains headers {}'.format(required))


def _index_map(worksheet, header_row):
    header = next(worksheet.iter_rows(min_row=header_row, max_row=header_row, values_only=True))
    return {str(name).strip(): index for index, name in enumerate(header) if name}


def _column(positions, prefix, required=True):
    for name, index in positions.items():
        if name.startswith(prefix):
            return index
    if required:
        raise ValueError('column {!r} not found in sheet'.format(prefix))
    return None


def _value(row, index, default=None):
    if index is None or index >= len(row):
        return default
    return row[index]


def read_pricebook(path):
    workbook = openpyxl.load_workbook(path, data_only=True)

    catalog_sheet, catalog_header = _sheet_with_cells(workbook, ('Артикул', 'Наименование'))
    positions = _index_map(catalog_sheet, catalog_header)
    article_at = _column(positions, 'Артикул')
    name_at = _column(positions, 'Наименование')
    kind_at = _column(positions, 'Тип', required=False)
    catalog = [
        {'article': str(_value(row, article_at)).strip(),
         'name': _value(row, name_at),
         'kind': _value(row, kind_at)}
        for row in catalog_sheet.iter_rows(min_row=catalog_header + 1, values_only=True)
        if row and _value(row, article_at)
    ]

    rename_sheet, rename_header = _sheet_with_cells(
        workbook, ('Старый артикул', 'Новый артикул'))
    positions = _index_map(rename_sheet, rename_header)
    old_at = _column(positions, 'Старый артикул')
    new_at = _column(positions, 'Новый артикул')
    since_at = _column(positions, 'Дата перехода', required=False)
    renames = [
        {'old': str(_value(row, old_at)).strip(),
         'new': str(_value(row, new_at)).strip(),
         'since': _value(row, since_at)}
        for row in rename_sheet.iter_rows(min_row=rename_header + 1, values_only=True)
        if row and _value(row, old_at)
    ]

    history_sheet, history_header = _sheet_with_cells(
        workbook, ('Артикул', 'Действует с', 'Действует по'))
    positions = _index_map(history_sheet, history_header)
    article_at = _column(positions, 'Артикул')
    from_at = _column(positions, 'Действует с')
    to_at = _column(positions, 'Действует по')
    recommended_at = _column(positions, 'Рекомендованная цена')
    minimum_at = _column(positions, 'Минимально допустимая цена')

    history = []
    for row in history_sheet.iter_rows(min_row=history_header + 1, values_only=True):
        if not row or not _value(row, article_at):
            continue
        recommended = _value(row, recommended_at)
        minimum = _value(row, minimum_at)
        if recommended is None or minimum is None:
            raise ValueError(
                'price history for {!r} has empty amounts; formulas without cached '
                'values are not supported, recalculate the workbook first'.format(
                    _value(row, article_at)))
        history.append({
            'article': str(_value(row, article_at)).strip(),
            'valid_from': _value(row, from_at),
            'valid_to': _value(row, to_at),
            'recommended': recommended,
            'minimum': minimum,
        })

    manager_sheet, manager_header = _sheet_with_cells(
        workbook, ('Каноническое имя', 'Варианты написания в CRM'))
    positions = _index_map(manager_sheet, manager_header)
    canonical_at = _column(positions, 'Каноническое имя')
    variants_at = _column(positions, 'Варианты написания в CRM')
    hired_at = _column(positions, 'Дата выхода', required=False)
    fired_at = _column(positions, 'Дата увольнения', required=False)
    managers = [
        {'canonical': str(_value(row, canonical_at)).strip(),
         'variants': _value(row, variants_at),
         'hired': _value(row, hired_at),
         'fired': _value(row, fired_at)}
        for row in manager_sheet.iter_rows(min_row=manager_header + 1, values_only=True)
        if row and _value(row, canonical_at)
    ]

    return {
        'catalog': catalog,
        'renames': renames,
        'history': history,
        'managers': managers,
    }


def read_chats(path):
    chats = []
    seen_ids = set()
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            if not info.filename.lower().endswith('.txt'):
                continue
            try:
                text = archive.read(info).decode('utf-8-sig')
            except UnicodeDecodeError as error:
                raise ValueError('chat file is not valid UTF-8: {}'.format(info.filename)) from error
            chat = parse_chat(text, info.filename)
            if chat['chat_id'] in seen_ids:
                raise ValueError('duplicate chat ID in archive: {}'.format(chat['chat_id']))
            seen_ids.add(chat['chat_id'])
            chats.append(chat)
    return chats


def parse_chat(text, filename):
    lines = text.splitlines()
    if not lines:
        raise ValueError('empty chat file: {}'.format(filename))

    header = lines[0].strip()
    chat_match = re.search(r'Чат\s+(C\d+)', header)
    if not chat_match:
        raise ValueError('chat ID not found in header for file {}'.format(filename))
    filename_match = re.search(r'(C\d+)', Path(filename).name)
    if filename_match and filename_match.group(1) != chat_match.group(1):
        raise ValueError('chat ID mismatch between filename and header: {}'.format(filename))

    order_match = re.search(r'заказ\s+([A-Za-zА-Яа-яЁё]-?\s?\d+)', header)
    manager_match = re.search(r'менеджер\s+(.+)$', header)
    client_match = re.search(r'клиент\s+([^|]+?)\s*\|', header)

    messages = []
    for line_number, line in enumerate(lines[1:], start=2):
        text = line.strip()
        if not text:
            continue
        match = _MESSAGE_RE.match(text)
        if not match:
            raise ValueError(
                'unrecognized message format at line {} in {}'.format(line_number, filename))
        stamp = parse_datetime('{} {}'.format(match.group(1), match.group(2)))
        messages.append({'at': stamp, 'sender': match.group(3), 'text': match.group(4).strip()})

    if not messages:
        raise ValueError('no messages parsed in {}'.format(filename))

    return {
        'chat_id': chat_match.group(1),
        'order_raw': order_match.group(1) if order_match else None,
        'manager_raw': manager_match.group(1).strip() if manager_match else None,
        'client_raw': client_match.group(1).strip() if client_match else None,
        'messages': messages,
    }


def find_data_dir(root):
    root = Path(root)
    if not root.is_dir():
        raise NotADirectoryError('data directory not found: {}'.format(root))

    candidates = [
        directory for directory in [root] + [path for path in root.rglob('*') if path.is_dir()]
        if all((directory / name).is_file() for name in DATA_FILES)
    ]
    if not candidates:
        raise FileNotFoundError(
            'data files not found under {}: {}'.format(root, ', '.join(DATA_FILES)))
    if len(candidates) > 1:
        locations = ', '.join(str(path.relative_to(root)) for path in candidates)
        raise ValueError('multiple complete datasets found under {}: {}'.format(root, locations))
    return candidates[0]


def load_dataset(data_dir):
    directory = find_data_dir(data_dir)
    return {
        'crm': read_crm(directory / CRM_FILENAME),
        'bank': read_bank(directory / BANK_FILENAME),
        'pricebook': read_pricebook(directory / PRICEBOOK_FILENAME),
        'chats': read_chats(directory / CHATS_FILENAME),
    }
