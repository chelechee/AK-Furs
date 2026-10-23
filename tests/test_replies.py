import pytest

from akfurs.replies import (
    GREETING_EMOJI,
    apply_emoji_policy,
    build_client_reply,
    check_emoji_policy,
    client_used_emoji,
    contains_emoji,
    count_emoji,
)


CLIENT_WITH_EMOJI = {
    'chat_id': 'C9001',
    'messages': [
        {'sender': 'Клиент', 'text': 'Добрый вечер! Жилет ещё есть? 🙂'},
        {'sender': 'Менеджер', 'text': 'Здравствуйте! Подскажите размер.'},
    ],
}

CLIENT_WITHOUT_EMOJI = {
    'chat_id': 'C9002',
    'messages': [
        {'sender': 'Клиент', 'text': 'Добрый вечер! Жилет ещё есть?'},
        {'sender': 'Менеджер', 'text': 'Здравствуйте! Подскажите размер.'},
    ],
}


def test_client_emoji_detection_uses_only_client_messages():
    assert client_used_emoji(CLIENT_WITH_EMOJI) is True
    assert client_used_emoji(CLIENT_WITHOUT_EMOJI) is False


def test_reply_gets_exactly_one_emoji_after_greeting_when_client_used_one():
    reply = build_client_reply(
        'Здравствуйте!',
        ['По имеющимся данным, жилет стоит 252 000 ₽.', 'Подберу удобное время примерки.'],
        client_used_emoji(CLIENT_WITH_EMOJI),
    )
    assert count_emoji(reply) == 1
    assert reply.startswith('Здравствуйте! ' + GREETING_EMOJI)
    assert not reply.startswith(GREETING_EMOJI)
    check_emoji_policy(reply, True)


def test_reply_has_no_emoji_when_client_used_none():
    reply = build_client_reply(
        'Здравствуйте!',
        ['По имеющимся данным, жилет стоит 252 000 ₽.'],
        client_used_emoji(CLIENT_WITHOUT_EMOJI),
    )
    assert not contains_emoji(reply)
    check_emoji_policy(reply, False)


def test_existing_emoji_is_removed_when_client_used_none():
    text = 'Здравствуйте! 🙂 Жилет стоит 252 000 ₽ 👍'
    cleaned = apply_emoji_policy(text, False)
    assert not contains_emoji(cleaned)
    assert cleaned == 'Здравствуйте! Жилет стоит 252 000 ₽'


def test_extra_emoji_collapse_to_one_after_greeting():
    text = 'Здравствуйте! 🙂🙂 Жилет стоит 252 000 ₽'
    result = apply_emoji_policy(text, True)
    assert count_emoji(result) == 1
    assert result.startswith('Здравствуйте! ' + GREETING_EMOJI)


def test_reply_must_not_start_with_emoji():
    with pytest.raises(ValueError, match='must not start with an emoji'):
        check_emoji_policy(GREETING_EMOJI + ' Здравствуйте! Жилет в наличии.', True)


def test_policy_rejects_emoji_in_greeting_less_reply():
    with pytest.raises(ValueError, match='textual greeting'):
        apply_emoji_policy('Жилет в наличии 🙂', True)


def test_policy_rejects_two_emoji_and_wrong_position():
    with pytest.raises(ValueError, match='exactly one emoji'):
        check_emoji_policy('Здравствуйте! {} {} Текст.'.format(GREETING_EMOJI, GREETING_EMOJI), True)
    with pytest.raises(ValueError, match='must follow the greeting'):
        check_emoji_policy('Здравствуйте! Текст. ' + GREETING_EMOJI, True)
    with pytest.raises(ValueError, match='must contain exactly one'):
        check_emoji_policy('Здравствуйте! Текст.', True)
    with pytest.raises(ValueError, match='although the client used none'):
        check_emoji_policy('Здравствуйте! {} Текст.'.format(GREETING_EMOJI), False)
