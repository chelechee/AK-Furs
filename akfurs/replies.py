"""Генератор ответов клиентам и правило эмодзи.

Правило (Q5b и любые будущие ответы):
- эмодзи ставится только если клиент сам использовал эмодзи в переписке;
- в этом случае в ответе ровно один эмодзи, сразу после текстового приветствия;
- если клиент эмодзи не использовал, ответ без эмодзи;
- сообщение никогда не начинается с эмодзи.
"""

import re

GREETING_EMOJI = '\U0001F642'

_EMOJI_CHAR = '[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F]'
_EMOJI_CLUSTER = re.compile(_EMOJI_CHAR + '(?:\u200d' + _EMOJI_CHAR + ')*')
_LEADING_EMOJI = re.compile(r'^\s*' + _EMOJI_CHAR)
_GREETING = re.compile(
    r'^\s*((?:здравствуйте|здравствуй|добрый\s+день|добрый\s+вечер|доброе\s+утро|'
    r'доброго\s+дня)[^!.\n]{0,40}[!.])',
    re.IGNORECASE,
)


def contains_emoji(text):
    return _EMOJI_CLUSTER.search(text) is not None


def count_emoji(text):
    return len(_EMOJI_CLUSTER.findall(text))


def strip_emoji(text):
    cleaned = _EMOJI_CLUSTER.sub('', text)
    return re.sub(r'[ \t]{2,}', ' ', cleaned).strip()


def client_used_emoji(chat, client_label='Клиент'):
    return any(contains_emoji(message['text']) for message in chat['messages']
               if message.get('sender') == client_label)


def split_greeting(text):
    match = _GREETING.match(text)
    if not match:
        return None, text.strip()
    return match.group(1), text[match.end():].lstrip()


def apply_emoji_policy(text, client_emoji, brand_emoji=False):
    """Приводит текст ответа к правилу эмодзи и возвращает готовое сообщение."""
    body = text.strip() if brand_emoji else strip_emoji(text)
    if brand_emoji:
        return body
    if not client_emoji:
        return body

    greeting, rest = split_greeting(body)
    if greeting is None:
        raise ValueError('client reply must start with a textual greeting: {!r}'.format(text[:40]))
    return '{} {} {}'.format(greeting, GREETING_EMOJI, rest).strip()


def check_emoji_policy(text, client_emoji, brand_emoji=False):
    """Проверяет готовый ответ. Возвращает None, при нарушении правила бросает ValueError."""
    if _LEADING_EMOJI.match(text):
        raise ValueError('reply must not start with an emoji')
    if contains_emoji(text):
        if not client_emoji and not brand_emoji:
            raise ValueError('reply contains an emoji although the client used none')
        if count_emoji(text) != 1:
            raise ValueError('reply must contain exactly one emoji, found {}'.format(
                count_emoji(text)))
        greeting, rest = split_greeting(text)
        if greeting is None:
            raise ValueError('reply must start with a textual greeting')
        if brand_emoji:
            return
        if not rest.startswith(GREETING_EMOJI):
            raise ValueError('emoji must follow the greeting sentence')
    elif client_emoji or brand_emoji:
        raise ValueError('client used an emoji, so the reply must contain exactly one')


def build_client_reply(greeting, paragraphs, client_emoji):
    """Собирает ответ из приветствия и абзацев, применяя правило эмодзи."""
    blocks = [greeting] + [block for block in paragraphs if block]
    text = '\n\n'.join(block.strip() for block in blocks)
    reply = apply_emoji_policy(text, client_emoji)
    check_emoji_policy(reply, client_emoji)
    return reply
