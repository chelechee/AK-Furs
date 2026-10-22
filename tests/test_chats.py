import pytest

from akfurs.chats import first_mentions, is_invitation, is_price, solve_q4
from akfurs.io_loaders import read_chats


@pytest.mark.parametrize('text', [
    'Приглашаю на примерку в ателье — когда вам удобно?',
    'Когда сможете подъехать на примерку?',
    'Лучше приезжайте к нам в ателье на примерку, всё покажем вживую!',
    'Давайте я запишу вас на встречу в шоурум, там и подберём.',
])
def test_invitation_templates(text):
    assert is_invitation(text)


@pytest.mark.parametrize('text', [
    'Можем оплатить в 2-3 платежа.',
    'Возможна предоплата 30%, остальное при получении.',
    'Наш шоурум находится у метро Фрунзенская, работаем ежедневно с 10 до 21.',
    'Все изделия шьём в нашем ателье, мерки снимаем индивидуально.',
])
def test_numbers_without_money_are_not_prices(text):
    assert not is_price(text)


@pytest.mark.parametrize('text', [
    'Цена с учётом всех работ: 53 000 ₽.',
    'Стоимость этой модели — 158 тыс..',
    'Изначальная стоимость 5 млн.',
    'Стоимость этой модели — 53 000.',
    'Цена с учётом всех работ: сто пятьдесят восемь тысяч рублей.',
    'Для вас итоговая — два миллиона двести тысяч рублей, это лучшее, что могу сделать.',
])
def test_price_recognition(text):
    assert is_price(text)


@pytest.fixture(scope='module')
def chats(data_dir):
    return read_chats(data_dir / '04_client_chats.zip')


def test_every_chat_has_exactly_one_invitation(chats):
    for chat in chats:
        invitations = [message for message in chat['messages']
                       if message['sender'] == 'Менеджер' and is_invitation(message['text'])]
        assert len(invitations) == 1, chat['chat_id']


def test_only_unfinished_chat_lacks_a_price(chats):
    missing = [chat['chat_id'] for chat in chats if first_mentions(chat)[1] is None]
    assert missing == ['C0010']


def test_client_messages_are_ignored(chats):
    chat = {
        'chat_id': 'C9999',
        'messages': [
            {'at': None, 'sender': 'Клиент', 'text': 'А сколько стоит? 300 000 ₽?'},
        ],
    }
    assert solve_q4([chat]) == []


def test_chat_without_invitation_is_ignored():
    from datetime import datetime
    chat = {
        'chat_id': 'C9998',
        'messages': [
            {'at': datetime(2025, 1, 1, 10, 0), 'sender': 'Менеджер',
             'text': 'Цена — 50 000 ₽.'},
        ],
    }
    assert solve_q4([chat]) == []


def test_flagged_chats_are_sorted_and_unique(chats):
    flagged = solve_q4(chats)
    assert flagged == sorted(flagged)
    assert len(flagged) == len(set(flagged))


def test_violation_count(chats):
    assert len(solve_q4(chats)) == 22


def test_minimal_synthetic_violation():
    from datetime import datetime
    chat = {
        'chat_id': 'C0001',
        'messages': [
            {'at': datetime(2025, 1, 1, 10, 0), 'sender': 'Менеджер',
             'text': 'Приглашаю на примерку в ателье.'},
            {'at': datetime(2025, 1, 1, 10, 5), 'sender': 'Менеджер',
             'text': 'Цена — 50 000 ₽.'},
        ],
    }
    assert solve_q4([chat]) == ['C0001']
