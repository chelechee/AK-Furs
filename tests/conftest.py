import shutil
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(scope='session')
def data_dir(tmp_path_factory):
    directory = ROOT / 'data'
    if not directory.is_dir():
        pytest.skip('raw data is not available')

    from akfurs.io_loaders import find_data_files, read_chats

    try:
        files = find_data_files(directory)
    except (FileNotFoundError, ValueError):
        pytest.skip('complete, unambiguous raw data is not available')

    aliases = {
        'crm': '01_crm_orders_export.csv',
        'bank': '02_bank_statement_rub.csv',
        'pricebook': '03_catalog_prices_reference.xlsx',
        'chats': '04_client_chats.zip',
    }
    normalized = tmp_path_factory.mktemp('input-data')
    for role, filename in aliases.items():
        if role != 'chats' or zipfile.is_zipfile(files[role]):
            shutil.copyfile(files[role], normalized / filename)
            continue
        with zipfile.ZipFile(normalized / filename, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for chat in read_chats(files[role]):
                header = ['Чат {}'.format(chat['chat_id'])]
                if chat['client_raw']:
                    header.append('клиент {}'.format(chat['client_raw']))
                if chat['order_raw']:
                    header.append('заказ {}'.format(chat['order_raw']))
                if chat['manager_raw']:
                    header.append('менеджер {}'.format(chat['manager_raw']))
                lines = [' | '.join(header)]
                lines.extend('[{}] {}: {}'.format(
                    message['at'].strftime('%d.%m.%Y %H:%M:%S'),
                    message['sender'], message['text'])
                    for message in chat['messages'])
                archive.writestr('{}.txt'.format(chat['chat_id']),
                                 '\n'.join(lines) + '\n')
    return normalized
