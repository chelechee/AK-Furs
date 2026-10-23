import shutil
import zipfile
from pathlib import Path

import openpyxl
import pytest

from akfurs.io_loaders import (
    find_data_files,
    identify_file,
    load_dataset,
    parse_chat,
    read_bank,
    read_chats,
    read_crm,
    read_pricebook,
    CRM_REQUIRED,
    _sheet_with_cells,
)
from akfurs.normalize import order_no, parse_date

ROOT = Path(__file__).resolve().parents[1]


def test_crm_rows_and_columns(data_dir):
    rows = read_crm(data_dir / '01_crm_orders_export.csv')
    assert rows
    assert set(rows[0]) == set(CRM_REQUIRED)


def test_every_crm_date_and_order_parses(data_dir):
    rows = read_crm(data_dir / '01_crm_orders_export.csv')
    for row in rows:
        order_no(row['Номер заказа'])
        parse_date(row['Дата создания'])


def test_bank_header_is_skipped(data_dir):
    rows = read_bank(data_dir / '02_bank_statement_rub.csv')
    assert rows
    assert rows[0]['kind'] == 'Поступление'
    assert rows[0]['purpose']
    assert all(row['amount_raw'] for row in rows)


def test_pricebook_sheets(data_dir):
    book = read_pricebook(data_dir / '03_catalog_prices_reference.xlsx')
    assert len(book['catalog']) == 30
    assert len(book['renames']) == 8
    assert len(book['history']) == 120
    assert len(book['managers']) == 5


def test_pricebook_periods_cover_all_articles(data_dir):
    book = read_pricebook(data_dir / '03_catalog_prices_reference.xlsx')
    articles = {entry['article'] for entry in book['history']}
    catalog = {entry['article'] for entry in book['catalog']}
    assert articles == catalog
    for article in catalog:
        periods = [h for h in book['history'] if h['article'] == article]
        assert len(periods) == 4


def test_chats_count_and_ids(data_dir):
    chats = read_chats(data_dir / '04_client_chats.zip')
    assert chats
    ids = [chat['chat_id'] for chat in chats]
    assert len(set(ids)) == len(chats)
    assert ids == sorted(ids)


def test_current_rar_archive_is_detected_and_read():
    source = find_data_files(ROOT / 'data')['chats']
    if source.suffix.lower() != '.rar':
        pytest.skip('current chat input is not a RAR archive')
    assert identify_file(source) == 'chats'
    chats = read_chats(source)
    assert chats
    assert len({chat['chat_id'] for chat in chats}) == len(chats)


def test_loose_chat_text_files_are_loaded_as_one_input(data_dir, tmp_path):
    for name in ('01_crm_orders_export.csv', '02_bank_statement_rub.csv',
                 '03_catalog_prices_reference.xlsx'):
        shutil.copyfile(data_dir / name, tmp_path / name)
    with zipfile.ZipFile(data_dir / '04_client_chats.zip') as archive:
        names = [name for name in archive.namelist() if name.lower().endswith('.txt')]
        assert len(names) >= 2
        for name in names[:2]:
            (tmp_path / Path(name).name).write_bytes(archive.read(name))

    detected = find_data_files(tmp_path)
    assert detected['chats'] == tmp_path
    chats = read_chats(detected['chats'])
    assert len(chats) == 2
    assert [chat['chat_id'] for chat in chats] == sorted(
        chat['chat_id'] for chat in chats)


def test_chat_messages_have_time_and_sender(data_dir):
    chats = read_chats(data_dir / '04_client_chats.zip')
    total = 0
    for chat in chats:
        assert chat['messages']
        for message in chat['messages']:
            assert message['sender'] in ('Клиент', 'Менеджер')
            assert message['text']
        total += len(chat['messages'])
    assert total > 0


def test_chat_order_references_are_parseable(data_dir):
    book = load_dataset(data_dir)
    references = [chat['order_raw'] for chat in book['chats'] if chat['order_raw']]
    assert references
    assert all(order_no(reference) is not None for reference in references)


def test_parse_chat_rejects_file_without_header():
    with pytest.raises(ValueError):
        parse_chat('пустой файл', 'x.txt')


def test_parse_chat_rejects_unknown_message_line():
    text = 'Чат C9999 | заказ A-1 | менеджер X | клиент Y\nэто не сообщение'
    with pytest.raises(ValueError, match='unrecognized message'):
        parse_chat(text, 'x.txt')


def test_parse_chat_error_does_not_echo_message_text():
    private_text = 'Клиент: секретная тестовая реплика'
    text = 'Чат C9999 | заказ A-1 | менеджер X | клиент Y\n' + private_text
    with pytest.raises(ValueError) as error:
        parse_chat(text, 'x.txt')
    assert private_text not in str(error.value)


def test_read_chats_rejects_duplicate_chat_ids(tmp_path):
    archive_path = tmp_path / 'duplicate.zip'
    chat_text = (
        'Чат C9999 | заказ A-1 | менеджер X | клиент Y\n'
        '[01.01.2025 10:00] Менеджер: Здравствуйте\n'
    )
    with zipfile.ZipFile(archive_path, 'w') as archive:
        archive.writestr('one.txt', chat_text)
        archive.writestr('two.txt', chat_text)
    with pytest.raises(ValueError, match='duplicate chat ID'):
        read_chats(archive_path)


def test_parse_chat_rejects_filename_header_id_mismatch():
    text = (
        'Чат C9999 | заказ A-1 | менеджер X | клиент Y\n'
        '[01.01.2025 10:00] Менеджер: Здравствуйте\n'
    )
    with pytest.raises(ValueError, match='chat ID mismatch'):
        parse_chat(text, 'C0001.txt')


def _copy_renamed(data_dir, target, names):
    target.mkdir(parents=True, exist_ok=True)
    for source, renamed in names.items():
        shutil.copyfile(data_dir / source, target / renamed)
    return target


RENAMED = {
    '01_crm_orders_export.csv': 'orders.data',
    '02_bank_statement_rub.csv': 'ledger.txt',
    '03_catalog_prices_reference.xlsx': 'catalog.bin',
    '04_client_chats.zip': 'messages.archive',
}


def test_roles_are_detected_by_content_not_by_name(data_dir, tmp_path):
    folder = _copy_renamed(data_dir, tmp_path / 'выгрузка без имён', RENAMED)
    detected = find_data_files(folder)
    assert {role: path.name for role, path in detected.items()} == {
        'crm': 'orders.data',
        'bank': 'ledger.txt',
        'pricebook': 'catalog.bin',
        'chats': 'messages.archive',
    }
    dataset = load_dataset(folder)
    assert dataset['crm']
    assert dataset['bank']
    assert dataset['chats']


def test_rar_chat_archive_is_detected_and_read():
    files = find_data_files(ROOT / 'data')
    source = files['chats']
    if source.suffix.lower() != '.rar':
        pytest.skip('current input is not a RAR archive')
    assert identify_file(source) == 'chats'
    chats = read_chats(source)
    assert chats
    assert len({chat['chat_id'] for chat in chats}) == len(chats)


def test_loose_chat_text_files_are_loaded_as_one_input(data_dir, tmp_path):
    for name in ('01_crm_orders_export.csv', '02_bank_statement_rub.csv',
                 '03_catalog_prices_reference.xlsx'):
        shutil.copyfile(data_dir / name, tmp_path / name)
    chat_file = data_dir / '04_client_chats.zip'
    with zipfile.ZipFile(chat_file) as archive:
        chat_names = [name for name in archive.namelist() if name.lower().endswith('.txt')]
        assert len(chat_names) >= 2
        for name in chat_names[:2]:
            (tmp_path / Path(name).name).write_bytes(archive.read(name))

    detected = find_data_files(tmp_path)
    assert detected['chats'] == tmp_path
    chats = read_chats(detected['chats'])
    assert len(chats) == 2
    assert [chat['chat_id'] for chat in chats] == sorted(
        chat['chat_id'] for chat in chats)


def test_pricebook_is_detected_through_hidden_sheet(data_dir, tmp_path):
    path = tmp_path / 'hidden-history.xlsx'
    shutil.copyfile(data_dir / '03_catalog_prices_reference.xlsx', path)
    workbook = openpyxl.load_workbook(path)
    sheet, _ = _sheet_with_cells(workbook, ('Артикул', 'Действует с', 'Действует по'))
    sheet.sheet_state = 'hidden'
    workbook.save(path)
    assert identify_file(path) == 'pricebook'
    assert read_pricebook(path)['history']


def test_unknown_files_are_ignored_but_missing_role_is_reported(data_dir, tmp_path):
    folder = _copy_renamed(data_dir, tmp_path / 'без чатов', {
        key: value for key, value in RENAMED.items() if key != '04_client_chats.zip'})
    (folder / 'notes.txt').write_text('служебная записка', encoding='utf-8')
    with pytest.raises(FileNotFoundError) as error:
        find_data_files(folder)
    message = str(error.value)
    assert 'missing: chats' in message
    assert 'notes.txt' in message


def test_ambiguous_sets_are_rejected_with_candidate_list(data_dir, tmp_path):
    _copy_renamed(data_dir, tmp_path / 'первый', RENAMED)
    _copy_renamed(data_dir, tmp_path / 'второй', RENAMED)
    with pytest.raises(ValueError, match='multiple candidate input files') as error:
        find_data_files(tmp_path)
    message = str(error.value)
    crm_line = next(line for line in message.split('; ') if line.startswith('crm: ')
                    or line.startswith('crm:') or 'crm:' in line and 'orders.data' in line)
    assert 'первый' in crm_line and 'второй' in crm_line
    assert 'orders.data' in crm_line
    assert 'chats:' in message and 'messages.archive' in message


def test_changed_crm_structure_is_not_guessed(data_dir, tmp_path):
    folder = _copy_renamed(data_dir, tmp_path / 'новая структура', {
        key: value for key, value in RENAMED.items() if key != '01_crm_orders_export.csv'})
    text = (data_dir / '01_crm_orders_export.csv').read_text(encoding='utf-8-sig')
    (folder / 'orders.data').write_text(
        text.replace('Цена за ед.', 'Цена единицы', 1), encoding='utf-8-sig')
    with pytest.raises(FileNotFoundError, match='missing: crm'):
        find_data_files(folder)


def test_file_matching_two_roles_is_rejected(tmp_path):
    header = ';'.join((
        'Номер заказа', '№ строки', 'Дата создания', 'Клиент', 'Менеджер', 'Источник',
        'Артикул', 'Кол-во', 'Цена за ед.', 'Валюта', 'Скидка', 'Статус',
        'Комментарий', 'Выгружено', 'Дата операции', 'Сумма', 'Тип', 'Назначение платежа',
    ))
    path = tmp_path / 'both.csv'
    path.write_text(header + '\n', encoding='utf-8')
    with pytest.raises(ValueError, match='matches several input roles'):
        identify_file(path)
