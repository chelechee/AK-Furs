from decimal import Decimal

from .bank import build_payments, solve_q2
from .chats import solve_q4
from .orders import build_clean_lines, summarise
from .pricing import build_history, solve_q3

RUN_COMMAND = 'python solve.py data/ --out answers.json'

NOTES = (
    'Номера заказов принимаются только в распознаваемых форматах с латинской/кириллической '
    'A, «№» или словом «заказ»; ведущие нули незначимы. Строки дедуплицируются по паре '
    '«номер + № строки» по максимальному «Выгружено»; конфликтующие записи с одинаковым '
    'максимальным временем отклоняются, неразличимые по расчётным полям сворачиваются. '
    'Статус берётся только из поля «Статус»; неизвестное значение становится «В работе», '
    'комментарий статус не меняет. Для ДД/ММ/ГГГГ '
    'день считается первым; смешанные разделители цен трактуются по правому разделителю, '
    'одиночная запятая в группе из трёх цифр — разделитель тысяч; «тыс.» и «млн» умножают '
    'на 1 000 и 1 000 000. Скидка N% применяется '
    'к цене единицы; рублёвая скидка — к сумме строки с последующим делением на количество. '
    'Переименования артикулов применяются без учёта даты перехода. Поступление сопоставляется '
    'по явной ссылке на заказ, коду A-номер или номеру счёта, который в исходном справочном '
    'наборе соответствует номеру заказа; прочие документальные номера, суммы, даты и телефоны '
    'не используются. При несовпадении явно указанного заказа и счёта ссылка неоднозначна '
    'и отклоняется. Q2a считает заказ оплаченным, '
    'если оплачена хотя бы одна строка. Сумма Q2b сохраняет копейки; целая сумма выводится '
    'целым JSON-числом, дробная — точным десятичным числом. Q3 сравнивает цену за единицу '
    'с минимумом на дату создания; исключается только «Отменён», «Возврат» включён. '
    'В Q4 анализируются только реплики менеджера; цена требует денежного маркера либо '
    'контекста цены; отдельно названные бюджет, предоплата, скидка и сумма, приписанная клиенту, '
    'сами по себе не являются ценой товара. Отрицательные и цитируемые приглашения не считаются. События сортируются '
    'по времени, порядку реплик и позиции внутри сообщения. Чат без приглашения не нарушает '
    'правило; чат с приглашением и без цены считается нарушением (включая C0010). Q4 остаётся '
    'предварительной классификацией и требует ручной проверки новых/неоднозначных реплик.'
)

REQUIRED_KEYS = (
    'q1_unique_orders',
    'q1_unique_order_lines',
    'q2a_paid_orders_without_payment',
    'q2b_unidentified_payments_count',
    'q2b_unidentified_payments_sum_rub',
    'q3_price_violation_lines_total',
    'q3_price_violation_lines_by_manager',
    'q4_chats_meeting_before_price',
    'run_command',
    'notes',
)


def build_answers(dataset):
    pricebook = dataset['pricebook']
    lines = build_clean_lines(pricebook, dataset['crm'])
    unique_orders, unique_lines = summarise(lines)

    known_orders = {line.order_no for line in lines}
    payments = build_payments(dataset['bank'], known_orders)
    paid_without_payment, unidentified_count, unidentified_sum = solve_q2(lines, payments)

    periods = build_history(pricebook['history'])
    violations_total, violations_by_manager = solve_q3(lines, periods)

    return {
        'q1_unique_orders': unique_orders,
        'q1_unique_order_lines': unique_lines,
        'q2a_paid_orders_without_payment': paid_without_payment,
        'q2b_unidentified_payments_count': unidentified_count,
        'q2b_unidentified_payments_sum_rub': unidentified_sum,
        'q3_price_violation_lines_total': violations_total,
        'q3_price_violation_lines_by_manager': violations_by_manager,
        'q4_chats_meeting_before_price': solve_q4(dataset['chats']),
        'run_command': RUN_COMMAND,
        'notes': NOTES,
    }


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def validate(answers):
    missing = [key for key in REQUIRED_KEYS if key not in answers]
    if missing:
        raise ValueError('missing keys: {}'.format(', '.join(missing)))

    extra = [key for key in answers if key not in REQUIRED_KEYS]
    if extra:
        raise ValueError('unexpected keys: {}'.format(', '.join(extra)))

    for key in ('q1_unique_orders', 'q1_unique_order_lines',
                'q2b_unidentified_payments_count', 'q3_price_violation_lines_total'):
        value = answers[key]
        if not _is_int(value):
            raise TypeError('{} must be int, got {}'.format(key, type(value).__name__))
        if value < 0:
            raise ValueError('{} must be non-negative'.format(key))

    payment_sum = answers['q2b_unidentified_payments_sum_rub']
    if isinstance(payment_sum, bool) or not isinstance(payment_sum, (int, Decimal)):
        raise TypeError('q2b_unidentified_payments_sum_rub must be int or Decimal')
    if isinstance(payment_sum, Decimal) and not payment_sum.is_finite():
        raise ValueError('q2b_unidentified_payments_sum_rub must be finite')
    if payment_sum < 0:
        raise ValueError('q2b_unidentified_payments_sum_rub must be non-negative')

    breakdown = answers['q3_price_violation_lines_by_manager']
    if not isinstance(breakdown, dict):
        raise TypeError('q3_price_violation_lines_by_manager must be a dict')
    for manager, value in breakdown.items():
        if not isinstance(manager, str):
            raise TypeError('manager name must be a string: {!r}'.format(manager))
        if not manager.strip():
            raise ValueError('manager name must be non-empty')
        if not _is_int(value):
            raise TypeError('manager count must be int: {!r}'.format((manager, value)))
        if value < 0:
            raise ValueError('manager count must be non-negative: {!r}'.format((manager, value)))
    if sum(breakdown.values()) != answers['q3_price_violation_lines_total']:
        raise ValueError('q3 breakdown must sum to q3_price_violation_lines_total')

    q2a = answers['q2a_paid_orders_without_payment']
    if not isinstance(q2a, list):
        raise TypeError('q2a_paid_orders_without_payment must be a list')
    if any(not _is_int(item) for item in q2a):
        raise TypeError('q2a_paid_orders_without_payment must contain ints')
    if any(item < 0 for item in q2a):
        raise ValueError('q2a_paid_orders_without_payment must contain non-negative ints')
    if q2a != sorted(q2a):
        raise ValueError('q2a_paid_orders_without_payment must be sorted')
    if len(q2a) != len(set(q2a)):
        raise ValueError('q2a_paid_orders_without_payment must be unique')

    q4 = answers['q4_chats_meeting_before_price']
    if not isinstance(q4, list):
        raise TypeError('q4_chats_meeting_before_price must be a list')
    if any(not isinstance(item, str) or not item.strip() for item in q4):
        raise TypeError('q4_chats_meeting_before_price must contain non-empty strings')
    if q4 != sorted(q4):
        raise ValueError('q4_chats_meeting_before_price must be sorted')
    if len(q4) != len(set(q4)):
        raise ValueError('q4_chats_meeting_before_price must be unique')

    if not isinstance(answers['run_command'], str) or not answers['run_command'].strip():
        raise ValueError('run_command must be a non-empty string')
    if not isinstance(answers['notes'], str) or not answers['notes'].strip():
        raise ValueError('notes must be a non-empty string')

    return answers
