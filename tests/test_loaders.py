import zipfile

import pytest

from akfurs.io_loaders import (
    DATA_FILES,
    find_data_dir,
    load_dataset,
    parse_chat,
    read_bank,
    read_chats,
    read_crm,
    read_pricebook,
)
from akfurs.normalize import order_no, parse_date


def test_crm_rows_and_columns(data_dir):
    rows = read_crm(data_dir / '01_crm_orders_export.csv')
    assert len(rows) == 1493
    assert set(rows[0]) == {
        'Номер заказа', '№ строки', 'Дата создания', 'Клиент', 'Менеджер',
        'Источник', 'Артикул', 'Кол-во', 'Цена за ед.', 'Валюта',
        'Скидка', 'Статус', 'Комментарий', 'Выгружено',
    }


def test_every_crm_date_and_order_parses(data_dir):
    rows = read_crm(data_dir / '01_crm_orders_export.csv')
    for row in rows:
        order_no(row['Номер заказа'])
        parse_date(row['Дата создания'])


def test_bank_header_is_skipped(data_dir):
    rows = read_bank(data_dir / '02_bank_statement_rub.csv')
    assert len(rows) == 1217
    assert rows[0]['kind'] == 'Поступление'
    assert rows[0]['purpose'].startswith('Предоплата заказ 775')
    assert {row['currency'] for row in rows} == {'RUR'}


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
    assert len(chats) == 150
    ids = [chat['chat_id'] for chat in chats]
    assert len(set(ids)) == 150
    assert ids[0] == 'C0001'
    assert 'C0010' in ids


def test_chat_messages_have_time_and_sender(data_dir):
    chats = read_chats(data_dir / '04_client_chats.zip')
    total = 0
    for chat in chats:
        assert chat['messages']
        for message in chat['messages']:
            assert message['sender'] in ('Клиент', 'Менеджер')
            assert message['text']
        total += len(chat['messages'])
    assert total == 1271


def test_chat_orders_exist_in_crm(data_dir):
    book = load_dataset(data_dir)
    known = {order_no(row['Номер заказа']) for row in book['crm']}
    missing = [
        chat['chat_id'] for chat in book['chats']
        if chat['order_raw'] and order_no(chat['order_raw']) not in known
    ]
    assert missing == []


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


def test_find_data_dir_rejects_multiple_complete_datasets(tmp_path):
    for name in ('first', 'second'):
        folder = tmp_path / name
        folder.mkdir()
        for filename in DATA_FILES:
            (folder / filename).touch()
    with pytest.raises(ValueError, match='multiple complete datasets'):
        find_data_dir(tmp_path)
