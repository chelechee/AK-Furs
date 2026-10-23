import pytest

from akfurs.chats import first_mentions, is_invitation, is_price, solve_q4
from akfurs.io_loaders import read_chats


@pytest.mark.parametrize('text', [
    'Приглашаю на примерку в ателье — когда вам удобно?',
    'Когда сможете подъехать на примерку?',
    'Лучше приезжайте к нам в ателье на примерку, всё покажем вживую!',
    'Давайте я запишу вас на встречу в шоурум, там и подберём.',
    'Будет удобно приехать к нам на примерку?',
    'Предлагаю согласовать встречу в ателье.',
    'Я записала вас на примерку.',
    'Предлагаю посетить наш шоурум.',
    'Давайте подберём дату визита.',
    'Можете заглянуть к нам в ателье.',
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
    'Стоимость этой модели — 252000руб.',
    'Цена — 252тыс.',
    'Изначальная стоимость 5 млн.',
    'Стоимость этой модели — 53 000.',
    'Цена с учётом всех работ: сто пятьдесят восемь тысяч рублей.',
    'Для вас итоговая — два миллиона двести тысяч рублей, это лучшее, что могу сделать.',
])
def test_price_recognition(text):
    assert is_price(text)


@pytest.mark.parametrize('text', [
    'Модель 2024 года.',
    'Артикул 252000.',
    'Дом 12500.',
    'Модель 2024 г.',
    'Скидка 10% — действующее предложение.',
    'Ваш бюджет — 300 000 ₽.',
    'Вы назвали сумму 300 000 ₽.',
])
def test_non_price_numbers_are_not_prices(text):
    assert not is_price(text)


def test_price_without_currency_requires_price_context():
    assert is_price('Стоимость этой модели — 53 000.')
    assert not is_price('Модель 53 000.')
    assert is_price('252 тысячи')


def test_product_price_is_selected_after_customer_budget_reference():
    from datetime import datetime
    chat = {'chat_id': 'C9990', 'messages': [
        {'at': datetime(2025, 1, 1, 10, 0), 'sender': 'Менеджер',
         'text': 'Вы указали бюджет 300 000 ₽. Цена изделия — 400 000 ₽.'},
        {'at': datetime(2025, 1, 1, 10, 1), 'sender': 'Менеджер',
         'text': 'Приглашаю на примерку.'},
    ]}
    assert solve_q4([chat]) == []


@pytest.fixture(scope='module')
def chats(data_dir):
    return read_chats(data_dir / '04_client_chats.zip')


def test_loaded_chats_have_messages(chats):
    for chat in chats:
        assert chat['messages'], chat['chat_id']


def test_first_event_positions_are_well_formed(chats):
    from datetime import datetime

    for chat in chats:
        for event in first_mentions(chat):
            if event is not None:
                assert isinstance(event[0], datetime)
                assert isinstance(event[1], int)
                assert isinstance(event[2], int)


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
    assert len(solve_q4(chats)) <= len(chats)


def test_flagged_chat_ids_match_manual_audit(chats):
    if len(chats) != 150:
        pytest.skip('manual Q4 audit is for the 150-chat reference set')
    assert solve_q4(chats) == [
        'C0010', 'C0024', 'C0033', 'C0037', 'C0042', 'C0060', 'C0061',
        'C0065', 'C0066', 'C0068', 'C0070', 'C0079', 'C0081', 'C0088',
        'C0090', 'C0091', 'C0092', 'C0093', 'C0102', 'C0133', 'C0135',
        'C0136',
    ]


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


def test_negated_invitation_is_not_an_invitation():
    assert not is_invitation('Не приглашаю вас на примерку.')


def test_quoted_invitation_and_price_are_not_manager_events():
    assert not is_invitation('Вы написали: «Приглашаю вас на примерку».')
    assert not is_price('Клиент спрашивал: «Сколько стоит 252 000 ₽?»')


def test_same_message_event_order_uses_text_position():
    from datetime import datetime
    stamp = datetime(2025, 1, 1, 10, 0)
    invite_first = {'chat_id': 'C9991', 'messages': [
        {'at': stamp, 'sender': 'Менеджер',
         'text': 'Приглашаю на примерку; цена — 252 000 ₽.'},
    ]}
    price_first = {'chat_id': 'C9992', 'messages': [
        {'at': stamp, 'sender': 'Менеджер',
         'text': 'Цена — 252 000 ₽; приглашаю на примерку.'},
    ]}
    assert solve_q4([invite_first]) == ['C9991']
    assert solve_q4([price_first]) == []


def test_attached_currency_keeps_amount_position_in_same_message():
    from datetime import datetime
    chat = {'chat_id': 'C9989', 'messages': [
        {'at': datetime(2025, 1, 1, 10, 0), 'sender': 'Менеджер',
         'text': 'Приглашаю на примерку, цена 252000руб.'},
    ]}
    assert solve_q4([chat]) == ['C9989']


def test_q4_sorts_events_by_timestamp_not_input_order():
    from datetime import datetime
    chat = {'chat_id': 'C9993', 'messages': [
        {'at': datetime(2025, 1, 1, 10, 0), 'sender': 'Менеджер',
         'text': 'Приглашаю на примерку.'},
        {'at': datetime(2025, 1, 1, 8, 0), 'sender': 'Менеджер',
         'text': 'Цена — 252 000 ₽.'},
    ]}
    assert solve_q4([chat]) == []


def test_model_year_does_not_hide_a_missing_price_violation():
    from datetime import datetime
    chat = {'chat_id': 'C9994', 'messages': [
        {'at': datetime(2025, 1, 1, 10, 0), 'sender': 'Менеджер',
         'text': 'Модель 2024 года.'},
        {'at': datetime(2025, 1, 1, 10, 1), 'sender': 'Менеджер',
         'text': 'Приглашаю на примерку.'},
    ]}
    assert solve_q4([chat]) == ['C9994']
