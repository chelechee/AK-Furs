import re

_INVITE_MARKERS = (
    'приглаша',
    'приезжа',
    'примерк',
    'запишу вас',
    'встречу в шоурум',
    'подъехать',
)

_MONEY_UNITS = re.compile(r'(₽|руб|тыс|млн)')
_SPELLED_NUMBER = re.compile(r'(тысяч|миллион)')
_BIG_NUMBER = re.compile(r'\d{1,3}(?:[ \u00a0\u202f]\d{3})+|\d{4,}')
_DIGIT = re.compile(r'\d')

MANAGER = 'Менеджер'


def is_invitation(text):
    low = text.lower()
    return any(marker in low for marker in _INVITE_MARKERS)


def is_price(text):
    low = text.lower()
    if _SPELLED_NUMBER.search(low):
        return True
    if _MONEY_UNITS.search(low) and _DIGIT.search(low):
        return True
    return bool(_BIG_NUMBER.search(text))


def first_mentions(chat):
    first_invitation = None
    first_price = None
    for message in chat['messages']:
        if message['sender'] != MANAGER:
            continue
        text = message['text']
        if first_invitation is None and is_invitation(text):
            first_invitation = message['at']
        if first_price is None and is_price(text):
            first_price = message['at']
    return first_invitation, first_price


def solve_q4(chats):
    flagged = []
    for chat in chats:
        first_invitation, first_price = first_mentions(chat)
        if first_invitation is None:
            continue
        if first_price is None or first_invitation < first_price:
            flagged.append(chat['chat_id'])
    return sorted(flagged)
