import re

MANAGER = 'Менеджер'

_QUOTED_TEXT = re.compile(r'«[^»]*»|“[^”]*”|„[^“]*“|"[^"]*"')
_INVITATION_PATTERNS = tuple(re.compile(pattern, re.IGNORECASE) for pattern in (
    r'\bприглаша\w*',
    r'\bприезжайте\b',
    r'\bприезжай\b',
    r'\bприехать\b',
    r'\bподъехать\b',
    r'\bподъезжайте\b',
    r'\bподъедете\b',
    r'\bзапишу\s+вас\b',
    r'\bзапишем\s+вас\b',
    r'\bзапис\w*\s+вас\b',
    r'\bзапишемся\b',
    r'\bбудем\s+рады\s+видеть\b',
    r'\bжд[её]м\s+вас\b',
    r'\bбудем\s+ждать\s+вас\b',
    r'\b(?:приходите|заходите)\b',
    r'\b(?:можете|сможете|предлагаю|предлагаем|давайте|будет\s+удобно|'
    r'можно(?:\s+будет)?|готовы\s+ли\s+вы)\s+'
    r'(?:нам\s+)?(?:приехать|подъехать|заехать|заглянуть)\b',
    r'\b(?:предлагаю|предлагаем|можете|можно|давайте)\s+посетить\s+'
    r'(?:наш\s+)?(?:шоурум|ателье)\b',
    r'\b(?:давайте|предлагаю|предлагаем)\s+(?:встретиться|встретимся)\b',
    r'\b(?:согласовать|согласуем)\s+встречу\b',
    r'\b(?:подбер[её]м|давайте\s+подбер[её]м|предлагаю\s+подобрать)\s+'
    r'(?:дату|время)\s+(?:встречи|визита|примерки)\b',
    r'\bдоговоримся\s+о\s+встрече\b',
))
_NEGATED_ACTION = re.compile(r'\bне(?:\s+\w+){0,3}\s*$', re.IGNORECASE)

_MONEY_UNIT = re.compile(
    r'₽|\bруб(?:\.|ля|лей)?\b|(?<=\d)руб(?:\.|ля|лей)?|'
    r'\bтыс\.?\b|(?<=\d)тыс\.?|\bмлн\.?\b|(?<=\d)млн\.?',
    re.IGNORECASE,
)
_SPELLED_SCALE = re.compile(r'\b(?:тысяч\w*|миллион\w*)\b', re.IGNORECASE)
_NUMERAL_WORD = re.compile(
    r'\b(?:один|одна|одно|одну|две?|три|четыре|пять|шесть|семь|восемь|девять|'
    r'десять|одиннадцать|двенадцать|тринадцать|четырнадцать|пятнадцать|'
    r'шестнадцать|семнадцать|восемнадцать|девятнадцать|двадцать|тридцать|'
    r'сорок|пятьдесят|шестьдесят|семьдесят|восемьдесят|девяносто|сто|'
    r'двести|триста|четыреста|пятьсот|шестьсот|семьсот|восемьсот|девятьсот)\b',
    re.IGNORECASE,
)
_BIG_NUMBER = re.compile(
    r'(?<![\w])(?:\d{1,3}(?:[ \u00a0\u202f.,]\d{3})+(?:[,.]\d{1,2})?'
    r'|\d{4,}(?:[,.]\d{1,2})?)'
    r'(?=(?:\s*(?:₽|руб(?:\.|ля|лей)?|р\.?|тыс\.?|млн\.?))|[^\w]|$)',
)
_PRICE_CONTEXT = re.compile(
    r'\b(?:цен\w*|стоим\w*|итогов\w*|составит|'
    r'предлагаю\s+специальную\s+цену)\b',
    re.IGNORECASE,
)
_NON_PRICE_CONTEXT = re.compile(
    r'\b(?:бюджет\w*|предоплат\w*|аванс\w*|взнос\w*|скидк\w*|'
    r'платеж\w*|платёж\w*|рассрочк\w*|вы\s+(?:назвали|называли|указали|'
    r'озвучили|написали|сказали))\b',
    re.IGNORECASE,
)
_YEAR_REFERENCE = re.compile(r'\b\d{4}\s*(?:года|год|г\.(?!\w))', re.IGNORECASE)


def _without_quotes(text):
    return _QUOTED_TEXT.sub(' ', text)


def _invitation_match(text):
    cleaned = _without_quotes(text)
    matches = []
    for pattern in _INVITATION_PATTERNS:
        for match in pattern.finditer(cleaned):
            prefix = cleaned[max(0, match.start() - 40):match.start()]
            if _NEGATED_ACTION.search(prefix):
                continue
            matches.append(match)
    return min(matches, key=lambda match: match.start()) if matches else None


def is_invitation(text):
    return _invitation_match(text) is not None


def _price_evidence(text):
    cleaned = _without_quotes(text)
    low = cleaned.lower()
    has_digit = re.search(r'\d', cleaned) is not None
    has_number_word = _NUMERAL_WORD.search(low) is not None
    context = _PRICE_CONTEXT.search(low)
    if _NON_PRICE_CONTEXT.search(low) and not context:
        return None

    # An explicit currency/scale marker is strong evidence only when an amount
    # is also present. A bare year or SKU is not a price.
    if _MONEY_UNIT.search(low) and (has_digit or has_number_word):
        return cleaned
    if _SPELLED_SCALE.search(low) and (has_number_word or has_digit):
        return cleaned

    # Some chats omit the currency, but explicitly say "цена/стоимость X".
    # Remove years first so "модель 2024 года" does not become a price.
    no_years = _YEAR_REFERENCE.sub(' ', cleaned)
    context = _PRICE_CONTEXT.search(no_years)
    if context and (_BIG_NUMBER.search(no_years) or _SPELLED_SCALE.search(no_years)):
        return no_years
    return None


def is_price(text):
    return _price_evidence(text) is not None


def _price_position(text):
    evidence = _price_evidence(text)
    if evidence is None:
        return None

    context = _PRICE_CONTEXT.search(evidence)
    if context:
        suffix = evidence[context.end():]
        candidates = [match for match in (_BIG_NUMBER.search(suffix),
                                           _NUMERAL_WORD.search(suffix),
                                           _SPELLED_SCALE.search(suffix)) if match]
        if candidates:
            return min(candidates, key=lambda match: match.start()).start() + context.end()

    unit = _MONEY_UNIT.search(evidence)
    if unit:
        prefix = evidence[max(0, unit.start() - 100):unit.start()]
        candidates = [match for match in (_BIG_NUMBER.search(prefix),
                                           _NUMERAL_WORD.search(prefix),
                                           _SPELLED_SCALE.search(prefix)) if match]
        if candidates:
            return min(candidates, key=lambda match: match.start()).start() + max(0, unit.start() - 100)

    candidates = [match for match in (_BIG_NUMBER.search(evidence),
                                       _NUMERAL_WORD.search(evidence)) if match]
    return min(candidates, key=lambda match: match.start()).start() if candidates else 0


def first_mentions(chat):
    invitations = []
    prices = []
    for index, message in enumerate(chat['messages']):
        if message['sender'] != MANAGER:
            continue
        at = message.get('at')
        if at is None:
            raise ValueError('manager message in chat {} has no timestamp'.format(chat['chat_id']))
        invitation = _invitation_match(message['text'])
        if invitation:
            invitations.append((at, index, invitation.start()))
        price_position = _price_position(message['text'])
        if price_position is not None:
            prices.append((at, index, price_position))
    return (min(invitations) if invitations else None,
            min(prices) if prices else None)


def solve_q4(chats):
    flagged = []
    for chat in chats:
        first_invitation, first_price = first_mentions(chat)
        if first_invitation is None:
            continue
        if first_price is None or first_invitation < first_price:
            flagged.append(chat['chat_id'])
    return sorted(flagged)
