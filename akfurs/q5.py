"""Q5: записка руководителю и ответ клиентке, собранные из данных.

Все числа берутся из выгрузки, шаблон содержит только формулировки.
Ни один шаблонный фрагмент не должен содержать цифр: это проверяет тест.
"""

import re
from decimal import Decimal

from .bank import build_payments
from .chats import solve_q4
from .normalize import (
    STATUS_PAID,
    normalize_status,
    order_no,
    parse_discount,
    unit_price_after_discount,
)
from .orders import build_clean_lines
from .pricing import build_history, solve_q3
from .replies import apply_emoji_policy, check_emoji_policy, client_used_emoji

CHAT_ID = 'C0010'
MEMO_TITLE = 'Записка руководителю'
REPLY_TITLE = 'Ответ клиентке в чате C0010'
MEMO_DATE_PREFIX = 'AK Furs · итоги сверки данных · '
REPLY_DATE_PREFIX = 'AK Furs · ответ менеджера · '
MEMO_THEME = 'Тема: что показала сверка CRM, банка и цен'
MEMO_GREETING = 'Добрый день!'
PROPOSALS_TITLE = 'Что предлагаю.'
CLIENT_GREETING = (
    'Здравствуйте! Спасибо за ваш интерес к нашей модели ✨'
)
CLIENT_INVITATION = (
    'Будем рады пригласить вас на примерку: вживую вы сможете оценить оттенок меха и '
    'фактуру изделия при дневном свете. Мы работаем ежедневно с 10:00 до 21:00.'
)
CLIENT_QUESTION = (
    'Подскажите, пожалуйста, когда вам было бы удобно приехать? Я помогу согласовать '
    'время визита.'
)
CLIENT_ITEM_LABELS = {'жилетсобольнатуральный': 'жилет из натурального соболя'}
BUSINESS_HOURS = (Decimal(10), Decimal(21), Decimal(0))


def plural(count, one, few, many):
    number = abs(int(count)) % 100
    if 11 <= number <= 14:
        return many
    number %= 10
    if number == 1:
        return one
    if 2 <= number <= 4:
        return few
    return many


def _case(count, singular, plural_form):
    return singular if abs(int(count)) % 100 != 11 and abs(int(count)) % 10 == 1 else plural_form


def rub(value):
    return '{:,}'.format(int(Decimal(value))).replace(',', ' ')


def millions(value):
    amount = Decimal(value) / Decimal(1_000_000)
    if amount == 0:
        return '0 ₽'
    digits = 1 if abs(amount) >= 100 else 2
    text = format(amount, '.{}f'.format(digits)).replace('.', ',')
    return text + ' млн ₽'


def share(part, total):
    if Decimal(total) == 0:
        return '0%' if Decimal(part) == 0 else 'не определена'
    value = Decimal(part) / Decimal(total) * 100
    if value >= 5:
        text = str(int(value.quantize(Decimal('1'))))
    else:
        text = format(value.quantize(Decimal('0.1')), 'f').replace('.', ',')
        if text.endswith(',0'):
            text = text[:-2]
    return text + '%'


def _date(value):
    return value.strftime('%d.%m.%Y')


def _order_code(order):
    return 'A-{:05d}'.format(order)


def build_figures(dataset):
    crm = dataset['crm']
    pricebook = dataset['pricebook']

    groups = {}
    for row in crm:
        key = (order_no(row['Номер заказа']), int(str(row['№ строки']).strip()))
        groups.setdefault(key, []).append(row)
    duplicates = {key: rows for key, rows in groups.items() if len(rows) > 1}
    status_conflicts = {
        key: rows for key, rows in duplicates.items()
        if len({normalize_status(row['Статус']) for row in rows}) > 1
    }

    lines = build_clean_lines(pricebook, crm)
    unique_orders = len({line.order_no for line in lines})
    unique_lines = len(lines)

    known_orders = {line.order_no for line in lines}
    payments = build_payments(dataset['bank'], known_orders)
    total_inflow = sum((payment.amount for payment in payments), Decimal(0))
    unidentified = [payment for payment in payments if payment.order_no is None]
    unidentified_sum = sum((payment.amount for payment in unidentified), Decimal(0))
    paid_orders = {line.order_no for line in lines if line.status == STATUS_PAID}
    paid_without_payment = len(paid_orders - {payment.order_no for payment in payments
                                              if payment.order_no is not None})

    periods = build_history(pricebook['history'])
    violations_total, violations_by_manager = solve_q3(lines, periods)
    managers = sorted(violations_by_manager.items(), key=lambda item: (-item[1], item[0]))
    fired = {row['canonical']: row['fired'] for row in pricebook['managers']}

    chats = dataset['chats']
    flagged = solve_q4(chats)
    client = _client_figures(dataset, lines, pricebook)
    known_orders = {line.order_no for line in lines}
    chat_order_missing = sum(
        bool(chat['order_raw']) and order_no(chat['order_raw']) not in known_orders
        for chat in chats)

    return {
        'raw_rows': len(crm),
        'unique_orders': unique_orders,
        'unique_lines': unique_lines,
        'duplicate_lines': len(crm) - unique_lines,
        'duplicate_share': share(len(crm) - unique_lines, len(crm)),
        'status_conflict_groups': len(status_conflicts),
        'status_conflict_orders': len({key[0] for key in status_conflicts}),
        'paid_without_payment': paid_without_payment,
        'unidentified_count': len(unidentified),
        'unidentified_sum': millions(unidentified_sum),
        'unidentified_share': share(unidentified_sum, total_inflow),
        'total_inflow': millions(total_inflow),
        'violations_total': violations_total,
        'violations_by_manager': managers,
        'violations_top_name': managers[0][0] if managers else None,
        'violations_top_fired': _date(fired[managers[0][0]]) if managers and fired.get(
            managers[0][0]) else None,
        'chats_total': len(chats),
        'flagged_chats': len(flagged),
        'chat_order_missing_count': chat_order_missing,
        'client': client,
    }


def _normalized_text(value):
    return re.sub(r'[^0-9a-zа-яё]+', '', str(value or '').casefold())


def _normalized_client_id(value):
    normalized = _normalized_text(value)
    if re.fullmatch(r'кл\d+', normalized):
        return 'cl' + normalized[2:]
    return normalized


def _chat_item(chat, catalog):
    client_text = ' '.join(message['text'] for message in chat['messages']
                           if message['sender'] == 'Клиент')
    message_words = set(re.findall(r'[0-9a-zа-яё]+', client_text.casefold()))
    matches = []
    for entry in catalog:
        name = str(entry['name'] or '').strip()
        words = set(re.findall(r'[0-9a-zа-яё]+', name.casefold()))
        if words and words <= message_words:
            matches.append((len(words), name))
    if not matches:
        return None
    most_specific = max(length for length, _ in matches)
    names = {name for length, name in matches if length == most_specific}
    return next(iter(names)) if len(names) == 1 else None


def _client_figures(dataset, lines, pricebook):
    chat = next((item for item in dataset['chats'] if item['chat_id'] == CHAT_ID), None)
    if chat is None:
        return {
            'chat_id': CHAT_ID,
            'order_code': None,
            'item_name': None,
            'price': None,
            'qty': None,
            'discount_kind': None,
            'discount_percent': None,
            'discount_amount': None,
            'total': None,
            'created': None,
            'chat_end': None,
            'client_emoji': False,
            'crm_link_matches': False,
            'chat_present': False,
        }

    prices = {row['article']: row['name'] for row in pricebook['catalog']}
    order = order_no(chat['order_raw']) if chat['order_raw'] else None
    items = [line for line in lines if line.order_no == order] if order else []
    single = items[0] if len(items) == 1 else None
    mentioned_item = _chat_item(chat, pricebook['catalog'])
    chat_client = _normalized_client_id(chat['client_raw'])
    client_matches = bool(chat_client and items) and all(
        _normalized_client_id(line.client) == chat_client for line in items)
    crm_item_name = (str(prices.get(single.article, single.article)).strip()
                     if single is not None else None)
    item_matches = (mentioned_item is None or
                    (crm_item_name is not None
                     and _normalized_text(mentioned_item) == _normalized_text(crm_item_name)))
    crm_link_matches = client_matches and item_matches
    total = (sum((line.unit_after * line.qty for line in items), Decimal(0))
             if crm_link_matches else None)
    discount_kind = None
    discount_value = None
    if crm_link_matches and single is not None and single.discount_raw.strip():
        discount_kind, discount_value = parse_discount(single.discount_raw)

    return {
        'chat_id': CHAT_ID,
        'order_code': _order_code(order) if order is not None else None,
        'item_name': ((mentioned_item or crm_item_name.lower())
                      if crm_link_matches and crm_item_name else mentioned_item),
        'price': rub(single.price) if crm_link_matches and single is not None else None,
        'qty': sum(line.qty for line in items) if crm_link_matches else None,
        'discount_kind': discount_kind,
        'discount_percent': (format(discount_value, 'f').replace('.', ',')
                             if discount_kind == 'percent' else None),
        'discount_amount': (rub(discount_value) if discount_kind == 'absolute' else None),
        'total': rub(total) if total is not None else None,
        'created': _date(min(line.created for line in items)) if items else None,
        'chat_end': _date(chat['messages'][-1]['at']),
        'client_emoji': client_used_emoji(chat),
        'crm_link_matches': crm_link_matches,
        'chat_present': True,
    }


def memo_paragraphs(figures, today):
    top = figures['violations_top_name']
    rest = figures['violations_by_manager'][1:]
    if figures['violations_total']:
        third = ('{total} {unit} проданы ниже минимально допустимой цены.'.format(
            total=figures['violations_total'],
            unit=plural(figures['violations_total'], 'позиция', 'позиции', 'позиций')))
    else:
        third = 'Продаж ниже минимально допустимых цен не выявлено.'
    if top and figures['violations_total']:
        leader = '{count} из них — {name}'.format(
            count=figures['violations_by_manager'][0][1], name=top)
        if figures['violations_top_fired']:
            leader += ' (уволилась {})'.format(figures['violations_top_fired'])
        third += ' ' + leader
        if rest:
            third += ', ещё ' + ', '.join(
                '{count} — {name}'.format(count=count, name=name) for name, count in rest)
        third += '.'

    intro = ('Проверили {rows} {row_unit} заказов, банковские поступления, историю цен и '
             '{chats} {chat_unit}. Три главных вывода.').format(
        rows=figures['raw_rows'],
        row_unit=plural(figures['raw_rows'], 'строку', 'строки', 'строк'),
        chats=figures['chats_total'],
        chat_unit=plural(figures['chats_total'], 'переписку', 'переписки', 'переписок'))

    if figures['duplicate_lines']:
        first = ('В данных {lines} {line_unit} — {share} выгрузки. После очистки остаётся '
                 '{orders} {order_unit} и {positions} {position_unit}.').format(
            lines=figures['duplicate_lines'],
            line_unit=plural(figures['duplicate_lines'], 'лишняя строка', 'лишние строки',
                             'лишних строк'),
            share=figures['duplicate_share'],
            orders=figures['unique_orders'],
            order_unit=plural(figures['unique_orders'], 'заказ', 'заказа', 'заказов'),
            positions=figures['unique_lines'],
            position_unit=plural(figures['unique_lines'], 'позиция', 'позиции', 'позиций'))
        if figures['status_conflict_groups']:
            first += (' Статус различается в {groups} {group_unit} дублей, относящихся к '
                      '{affected} {affected_unit}.').format(
                groups=figures['status_conflict_groups'],
                group_unit=_case(figures['status_conflict_groups'], 'группе', 'группах'),
                affected=figures['status_conflict_orders'],
                affected_unit=_case(figures['status_conflict_orders'], 'заказу', 'заказам'))
        else:
            first += ' Статусы в повторных строках не расходятся.'
    else:
        first = ('Дубли строк не обнаружены: в выгрузке {orders} {order_unit} и '
                 '{positions} {position_unit}.').format(
            orders=figures['unique_orders'],
            order_unit=plural(figures['unique_orders'], 'заказ', 'заказа', 'заказов'),
            positions=figures['unique_lines'],
            position_unit=plural(figures['unique_lines'], 'позиция', 'позиции', 'позиций'))
    if figures['chat_order_missing_count']:
        first += (' В {missing} из {chats} переписок заказ из заголовка не найден в CRM.').format(
            missing=figures['chat_order_missing_count'], chats=figures['chats_total'])
    if not figures['client']['chat_present']:
        third += ' Переписка C0010 отсутствует в загруженном наборе; ответ клиентке не подготовлен.'
    elif not figures['client']['crm_link_matches']:
        third += (' Связь чата C0010 с записью CRM не подтверждается по клиенту или изделию; '
                  'цену из этой записи использовать нельзя до сверки.')

    money_findings = []
    if figures['paid_without_payment']:
        money_findings.append('{count} {unit} со статусом «Оплачен» не имеют поступлений.'.format(
            count=figures['paid_without_payment'],
            unit=plural(figures['paid_without_payment'], 'заказ', 'заказа', 'заказов')))
    if figures['unidentified_count']:
        money_findings.append('{count} {unit} на {sum} ({share} от всех поступлений, {total}) '
                              'не привязаны к заказу.'.format(
            count=figures['unidentified_count'],
            unit=plural(figures['unidentified_count'], 'поступление', 'поступления',
                        'поступлений'),
            sum=figures['unidentified_sum'], share=figures['unidentified_share'],
            total=figures['total_inflow']))
    if money_findings:
        second = 'Деньги сходятся не полностью. ' + ' '.join(money_findings)
    else:
        second = ('Расхождений по сверке поступлений не выявлено: нет оплаченных заказов '
                  'без поступлений и неопознанных платежей.')

    conclusions = [first, second, third]

    if not figures['client']['chat_present']:
        first_recommendation = (
            'Восстановить переписку C0010 и повторно проверить связь клиента с CRM; без '
            'исходного сообщения нельзя подготовить персональный ответ или назвать цену.')
    elif figures['chat_order_missing_count'] or not figures['client']['crm_link_matches']:
        first_recommendation = (
            'Проверить связи чатов с CRM: в {missing} переписках заказ не найден; по C0010 '
            'карточка CRM не совпадает с перепиской. До сверки не использовать привязанную '
            'цену в ответе клиентке.').format(missing=figures['chat_order_missing_count'])
    elif figures['paid_without_payment'] or figures['unidentified_count']:
        first_recommendation = (
            'Сделать номер заказа обязательным в назначении платежа и раз в неделю сверять '
            '«заказ ↔ поступление»; это поможет разобрать текущие расхождения и не терять '
            'новые платежи.')
    else:
        first_recommendation = (
            'Сохранять номер заказа в назначении платежа и продолжать еженедельную сверку '
            '«заказ ↔ поступление».')

    if figures['violations_total']:
        price_recommendation = (
            'Запретить оформление ниже минимальной цены без подтверждения руководителя и '
            'проверить продажи за период работы {name}.').format(name=top or 'команды')
    else:
        price_recommendation = (
            'Сохранять контроль соответствия продаж минимальной цене; нарушений в проверенных '
            'строках не выявлено.')
    if figures['flagged_chats']:
        chat_recommendation = ('Закрепить правило «сначала цена, потом приглашение»: порядок '
                               'нарушен в {flagged} из {chats} {unit}.').format(
            flagged=figures['flagged_chats'], chats=figures['chats_total'],
            unit=plural(figures['chats_total'], 'переписки', 'переписок', 'переписок'))
    else:
        chat_recommendation = ('Продолжать контролировать порядок «сначала цена, потом '
                               'приглашение»; нарушений в проверенных переписках не выявлено.')
    recommendations = [first_recommendation, price_recommendation + ' ' + chat_recommendation]

    numbered = ['{}. {}'.format(index, text)
                for index, text in enumerate(conclusions, start=1)]
    numbered += ['{}. {}'.format(index, text)
                 for index, text in enumerate(recommendations, start=1)]
    return [MEMO_TITLE, MEMO_DATE_PREFIX + today, MEMO_THEME, MEMO_GREETING, intro] + \
        numbered[:len(conclusions)] + [PROPOSALS_TITLE] + numbered[len(conclusions):]


def _client_price_sentence(client):
    if not client['crm_link_matches']:
        return ('Уточню актуальную стоимость и наличие изделия, о котором вы спрашиваете, и '
                'сообщу вам до визита. После этого вы сможете решить, подходит ли вам предложение.')
    if client['item_name'] and client['discount_kind'] == 'percent':
        normalized_item = _normalized_text(client['item_name'])
        item = CLIENT_ITEM_LABELS.get(normalized_item, client['item_name'].lower())
        item = item[0].upper() + item[1:]
        return ('{} стоит {} ₽. С учётом вашей скидки {}% стоимость составит {} ₽.'.format(
            item, client['price'], client['discount_percent'], client['total']))
    if client['item_name'] and client['discount_kind'] == 'absolute':
        base = ('В заказе указана цена {price} ₽ за {item} и скидка {amount} ₽; сумма по '
                'заказу — {total} ₽.')
        return base.format(item=client['item_name'], price=client['price'],
                           amount=client['discount_amount'], total=client['total'])
    if client['item_name']:
        base = ('В заказе указана цена {price} ₽ за {item}; скидка в записи не указана, '
                'сумма — {total} ₽.')
        return base.format(item=client['item_name'], price=client['price'],
                           total=client['total'])
    base = 'В заказе указано {count} {unit} на общую сумму {total} ₽.'
    count = client['qty'] or 1
    return base.format(count=count, unit=plural(count, 'позиция', 'позиции', 'позиций'),
                       total=client['total'])


def reply_paragraphs(figures, today):
    client = figures['client']
    if not client['chat_present']:
        return [
            REPLY_TITLE,
            REPLY_DATE_PREFIX + today,
            ('Ответ не сформирован: переписка C0010 отсутствует в текущем наборе. '
             'Не отправлять клиентке; восстановите чат и повторите расчёт.'),
        ]
    greeting = CLIENT_GREETING
    parts = [greeting, _client_price_sentence(client)]
    if client['crm_link_matches']:
        parts.extend((CLIENT_INVITATION, CLIENT_QUESTION))
    text = '\n\n'.join(parts)
    reply = apply_emoji_policy(text, client['client_emoji'], brand_emoji=True)
    check_emoji_policy(reply, client['client_emoji'], brand_emoji=True)
    return [
        REPLY_TITLE,
        REPLY_DATE_PREFIX + today,
        *reply.split('\n\n'),
    ]


def docx_texts(figures, today):
    """Q5 paragraphs: memo, separator, and a client reply without internal notes."""
    return memo_paragraphs(figures, today) + [''] + reply_paragraphs(figures, today)


def markdown(figures, today):
    memo = memo_paragraphs(figures, today)
    memo[0] = memo[0].upper()
    reply = reply_paragraphs(figures, today)
    reply[0] = reply[0].upper()
    return '\n\n'.join(memo) + '\n\n\n' + '\n\n'.join(reply) + '\n'


NUMBER_TOKEN = re.compile(r'\d[\d\s.,]*%?')
LIST_MARKER = re.compile(r'^(\d+)\.\s')
DATE = re.compile(r'\d{2}\.\d{2}\.\d{4}')
ORDER_CODE = re.compile(r'A-\d{5}')
CHAT_CODE = re.compile(r'C\d{4,}')


def unexpected_numbers(text, allowed):
    """Числа в тексте, которых нет среди вычисленных значений."""
    cleaned = DATE.sub(' ', text)
    cleaned = ORDER_CODE.sub(' ', cleaned)
    cleaned = CHAT_CODE.sub(' ', cleaned)
    cleaned = '\n'.join(LIST_MARKER.sub('', line) for line in cleaned.splitlines())
    found = set()
    for token in NUMBER_TOKEN.findall(cleaned):
        value = token.strip().rstrip('%').replace(' ', '').replace(',', '.')
        try:
            number = Decimal(value)
        except Exception:
            continue
        if number not in allowed:
            found.add(token.strip())
    return sorted(found)


def _collect_numbers(value, values):
    if isinstance(value, bool):
        return
    if isinstance(value, int):
        values.add(Decimal(value))
    elif isinstance(value, str):
        for token in NUMBER_TOKEN.findall(value):
            try:
                values.add(Decimal(token.rstrip('%').replace(' ', '').replace(',', '.')))
            except Exception:
                continue
    elif isinstance(value, dict):
        for item in value.values():
            _collect_numbers(item, values)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _collect_numbers(item, values)


def allowed_numbers(figures):
    values = set()
    _collect_numbers(figures, values)
    values.update(BUSINESS_HOURS)
    return values
