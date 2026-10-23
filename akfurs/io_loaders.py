import csv
import io
import os
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

import openpyxl

from .normalize import parse_datetime

ROLE_CRM = 'crm'
ROLE_BANK = 'bank'
ROLE_PRICEBOOK = 'pricebook'
ROLE_CHATS = 'chats'
ROLES = (ROLE_CRM, ROLE_BANK, ROLE_PRICEBOOK, ROLE_CHATS)

SKIPPED_DIRECTORIES = frozenset({
    '.git', '.hg', '.svn', '.venv', 'venv', '__pycache__', '.pytest_cache',
    '.mypy_cache', '.ruff_cache', 'handoff', 'employer_package',
})

CRM_REQUIRED = (
    'Номер заказа', '№ строки', 'Дата создания', 'Клиент', 'Менеджер', 'Источник',
    'Артикул', 'Кол-во', 'Цена за ед.', 'Валюта', 'Скидка', 'Статус',
    'Комментарий', 'Выгружено',
)

PRICEBOOK_TABLES = (
    ('Артикул', 'Наименование'),
    ('Старый артикул', 'Новый артикул'),
    ('Артикул', 'Действует с', 'Действует по'),
    ('Каноническое имя', 'Варианты написания в CRM'),
)

_MESSAGE_RE = re.compile(
    r'\[(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2}(?::\d{2})?)\]\s*(Клиент|Менеджер)\s*:\s*(.*)'
)
_CHAT_HEADER_RE = re.compile(r'Чат\s+(C\d+)')
_RAR_SIGNATURES = (b'Rar!\x1a\x07\x00', b'Rar!\x1a\x07\x01\x00')

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


def _header_names(row):
    return {str(value).strip() for value in row if str(value).strip()}


def _find_csv_header(text, required, description, max_lines=50):
    lines = text.splitlines()
    for index in range(min(len(lines), max_lines)):
        if not lines[index].strip():
            continue
        delimiter = detect_delimiter('\n'.join(lines[index:index + 5]))
        try:
            header = next(csv.reader([lines[index]], delimiter=delimiter))
        except (csv.Error, StopIteration):
            continue
        if set(required).issubset(_header_names(header)):
            return index, delimiter
    missing = [name for name in required]
    raise ValueError('{} header not found (expected columns: {})'.format(
        description, ', '.join(missing)))


def read_crm(path):
    text = decode_bytes(Path(path).read_bytes())
    header_index, delimiter = _find_csv_header(text, CRM_REQUIRED, 'CRM orders export')
    with io.StringIO(text) as handle:
        for _ in range(header_index):
            next(handle)
        reader = csv.DictReader(handle, delimiter=delimiter, skipinitialspace=True)
        rows = []
        for row in reader:
            if not any(str(value or '').strip() for value in row.values()):
                continue
            rows.append({str(key).strip(): (value if value is not None else '')
                         for key, value in row.items() if key is not None})
        return rows


def read_bank(path):
    text = decode_bytes(Path(path).read_bytes())
    header_index, delimiter = _find_csv_header(
        text, tuple(_BANK_COLUMNS[label] for label in _BANK_REQUIRED), 'bank statement')
    lines = text.splitlines()
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
    workbook = openpyxl.load_workbook(io.BytesIO(Path(path).read_bytes()), data_only=True)

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
    path = Path(path)
    entries = []
    if path.is_dir():
        for member in sorted(path.rglob('*')):
            if member.is_file() and member.suffix.lower() == '.txt' \
                    and _is_loose_chat_file(member):
                entries.append((str(member.relative_to(path)), member.read_bytes()))
    elif zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            entries = [(info.filename, archive.read(info))
                       for info in archive.infolist()
                       if not info.is_dir() and info.filename.lower().endswith('.txt')]
    elif _is_rar_file(path):
        entries = [(name, _read_rar_member(path, name))
                   for name in _rar_member_names(path)
                   if name.lower().endswith('.txt')]
    else:
        raise ValueError('chat input must be a ZIP/RAR archive or a directory of chat .txt files')

    for filename, raw in entries:
        try:
            text = raw.decode('utf-8-sig')
        except UnicodeDecodeError as error:
            raise ValueError('chat file is not valid UTF-8: {}'.format(filename)) from error
        chat = parse_chat(text, filename)
        if chat['chat_id'] in seen_ids:
            raise ValueError('duplicate chat ID in archive: {}'.format(chat['chat_id']))
        seen_ids.add(chat['chat_id'])
        chats.append(chat)
    if not chats:
        raise ValueError('no chat files found in {}'.format(path.name))
    return sorted(chats, key=lambda chat: chat['chat_id'])


def _is_loose_chat_file(path):
    """Identify an individual chat export without claiming arbitrary .txt files."""
    try:
        first_line = decode_bytes(Path(path).read_bytes()).splitlines()[:1]
    except (OSError, UnicodeError):
        return False
    return bool((first_line and _CHAT_HEADER_RE.search(first_line[0]))
                or re.fullmatch(r'C\d+\.txt', Path(path).name, re.IGNORECASE))


def _unrar_executable():
    configured = os.environ.get('UNRAR_TOOL')
    candidates = [configured] if configured else []
    candidates.extend(shutil.which(name) for name in ('UnRAR.exe', 'unrar.exe', 'unrar'))
    for variable in ('ProgramFiles', 'ProgramFiles(x86)'):
        base = os.environ.get(variable)
        if base:
            candidates.append(str(Path(base) / 'WinRAR' / 'UnRAR.exe'))
    local = os.environ.get('LOCALAPPDATA')
    if local:
        candidates.append(str(Path(local) / 'Programs' / 'WinRAR' / 'UnRAR.exe'))
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    raise FileNotFoundError(
        'RAR chat archive found, but UnRAR.exe is unavailable; install WinRAR or extract '
        'the chat .txt files into the data directory')


def _is_rar_file(path):
    try:
        with open(path, 'rb') as handle:
            signature = handle.read(8)
    except OSError:
        return False
    return any(signature.startswith(prefix) for prefix in _RAR_SIGNATURES)


def _run_unrar(arguments, path):
    executable = _unrar_executable()
    try:
        result = subprocess.run(
            [executable, *arguments, str(path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError('could not read RAR chat archive {}'.format(Path(path).name)) from error
    if result.returncode:
        raise ValueError('UnRAR could not read chat archive {}'.format(Path(path).name))
    return result.stdout


def _decode_member_names(raw):
    for encoding in ('utf-8-sig', 'mbcs', 'cp1251', 'cp866'):
        try:
            return raw.decode(encoding).splitlines()
        except (LookupError, UnicodeDecodeError):
            continue
    raise ValueError('RAR archive member names use an unsupported encoding')


def _rar_member_names(path):
    output = _run_unrar(['lb', '-p-'], path)
    return [name.strip() for name in _decode_member_names(output)
            if name.strip() and not name.strip().endswith(('\\', '/'))]


def _read_rar_member(path, member):
    executable = _unrar_executable()
    try:
        result = subprocess.run(
            [executable, 'p', '-inul', '-p-', str(path), member],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError('could not read chat file from RAR archive') from error
    if result.returncode:
        raise ValueError('could not extract a chat file from RAR archive')
    return result.stdout


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


def _is_pricebook(raw):
    """Книга содержит все четыре таблицы; скрытые листы учитываются наравне с видимыми."""
    try:
        workbook = openpyxl.load_workbook(io.BytesIO(raw), data_only=True, read_only=True)
    except Exception:
        return False
    try:
        headers = [
            _header_names(cell.value for cell in row)
            for worksheet in workbook.worksheets
            for row in worksheet.iter_rows(min_row=1, max_row=15)
        ]
    except Exception:
        return False
    finally:
        workbook.close()
    return all(any(set(required).issubset(header) for header in headers)
               for required in PRICEBOOK_TABLES)


def _is_chat_archive(raw):
    """ZIP с текстовыми файлами, где заголовок первого файла имеет формат «Чат C0001 | …»."""
    if not zipfile.is_zipfile(io.BytesIO(raw)):
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            for info in archive.infolist():
                if info.is_dir() or not info.filename.lower().endswith('.txt'):
                    continue
                try:
                    first_line = archive.read(info).decode('utf-8-sig').splitlines()[:1]
                except UnicodeDecodeError:
                    continue
                if first_line and re.search(r'Чат\s+C\d+', first_line[0]):
                    return True
    except (zipfile.BadZipFile, OSError):
        return False
    return False


def _is_rar_chat_archive(path):
    for name in _rar_member_names(path):
        if not name.lower().endswith('.txt'):
            continue
        try:
            text = _read_rar_member(path, name).decode('utf-8-sig')
        except UnicodeDecodeError:
            continue
        first_line = text.splitlines()[:1]
        if first_line and _CHAT_HEADER_RE.search(first_line[0]):
            return True
    return False


def identify_file(path):
    """Роль файла по содержимому. Возвращает None, если файл не является входным."""
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError:
        return None

    if _is_pricebook(raw):
        return ROLE_PRICEBOOK
    if _is_chat_archive(raw):
        return ROLE_CHATS
    if any(raw.startswith(signature) for signature in _RAR_SIGNATURES):
        return ROLE_CHATS if _is_rar_chat_archive(path) else None

    try:
        text = decode_bytes(raw)
    except (UnicodeDecodeError, UnicodeError):
        return None

    matches = []
    try:
        _find_csv_header(text, CRM_REQUIRED, 'CRM orders export')
    except ValueError:
        pass
    else:
        matches.append(ROLE_CRM)
    try:
        _find_csv_header(text, tuple(_BANK_COLUMNS[label] for label in _BANK_REQUIRED),
                         'bank statement')
    except ValueError:
        pass
    else:
        matches.append(ROLE_BANK)

    if len(matches) > 1:
        raise ValueError(
            'file {} matches several input roles ({}); refusing to guess'.format(
                path.name, ', '.join(matches)))
    return matches[0] if matches else None


def find_data_files(root):
    """Находит четыре входных файла по содержимому. Имена и расширения не учитываются."""
    root = Path(root)
    if not root.is_dir():
        raise NotADirectoryError('data directory not found: {}'.format(root))

    candidates = {role: [] for role in ROLES}
    unrecognized = []
    has_loose_chats = False
    for path in sorted(root.rglob('*')):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in SKIPPED_DIRECTORIES for part in relative.parts[:-1]):
            continue
        if path.suffix.lower() == '.txt' and _is_loose_chat_file(path):
            has_loose_chats = True
            continue
        role = identify_file(path)
        if role is None:
            unrecognized.append(str(relative))
        else:
            candidates[role].append(path)

    if has_loose_chats:
        candidates[ROLE_CHATS].append(root)

    missing = [role for role in ROLES if not candidates[role]]
    if missing:
        details = 'missing: {}'.format(', '.join(missing))
        if unrecognized:
            details += '; not recognized: {}'.format(', '.join(unrecognized))
        raise FileNotFoundError(
            'could not identify all input files by content under {} ({})'.format(root, details))

    ambiguous = {role: paths for role, paths in candidates.items() if len(paths) > 1}
    if ambiguous:
        details = '; '.join('{}: {}'.format(
            role, ', '.join(str(path.relative_to(root)) for path in paths))
            for role, paths in ambiguous.items())
        raise ValueError(
            'multiple candidate input files found under {}: {}'.format(root, details))

    return {role: paths[0] for role, paths in candidates.items()}


def load_dataset(data_dir):
    files = find_data_files(data_dir)
    return {
        'crm': read_crm(files[ROLE_CRM]),
        'bank': read_bank(files[ROLE_BANK]),
        'pricebook': read_pricebook(files[ROLE_PRICEBOOK]),
        'chats': read_chats(files[ROLE_CHATS]),
    }
