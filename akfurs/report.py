from .bank import build_payments, solve_q2
from .chats import solve_q4
from .orders import build_clean_lines, summarise
from .pricing import build_history, solve_q3

RUN_COMMAND = 'python solve.py data/ --out answers.json'

NOTES = (
    'Номер заказа приведён к целому: удалены все нецифровые символы, поэтому A-00075, А-75, '
    'a-75 и A75 дают 75. Строки заказов дедуплицированы по паре «номер заказа + № строки» '
    'с выбором записи по максимальному значению «Выгружено»; ничьи разрешаются по порядку '
    'строки в файле. Статусы приведены к четырём категориям по полю «Статус»; комментарий '
    'о возврате статус не меняет, так как правило ТЗ отсылает только к статусу. Даты разобраны '
    'в шести форматах, для записи ДД/ММ/ГГГГ принят порядок «день первым»: это единственное '
    'прочтение, при котором все даты разбираются и ни один платёж не оказывается раньше даты '
    'своего заказа. Цены разобраны с учётом обеих ролей запятой: если в числе есть и точка, '
    'и запятая, десятичным считается правый разделитель; если только запятая — она десятичная, '
    'кроме вида «1,234» с группами по три цифры, где она разделяет разряды. Суффикс «млн» '
    'умножает на 1 000 000. Скидка в процентах применяется к цене за единицу, скидка в рублях '
    'вычитается из суммы строки и приводится к цене за единицу делением на количество. '
    'Переименования артикулов применены безусловно, без учёта даты перехода. Платёж отнесён '
    'к заказу, если после удаления телефонов и дат в назначении остаётся номер существующего '
    'заказа; номера вне диапазона CRM считаются неопознанными. В Q2a заказ считается '
    'оплаченным, если статус «Оплачен» имеет хотя бы одна его строка; на текущих данных это '
    'правило ни на что не влияет, потому что после дедупликации смешанных статусов внутри '
    'заказа не остаётся. В Q3 сравнивается цена за единицу после скидки с минимальной ценой '
    'периода, действующего на дату создания заказа; исключены только строки «Отменён», '
    '«Возврат» включён. В разбивке Q3 перечислены только менеджеры с нарушениями, нулевые '
    'значения не добавляются. В Q4 учитываются только реплики менеджера, приглашением '
    'считаются упоминания примерки, встречи в шоуруме и записи, ценой — сумма в любой записи, '
    'включая прописью, «Изначальная стоимость» и число без указания валюты; чат, где цена '
    'не названа вообще (C0010), считается нарушением.'
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
        'q2b_unidentified_payments_sum_rub': int(unidentified_sum.to_integral_value()),
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
                'q2b_unidentified_payments_count', 'q2b_unidentified_payments_sum_rub',
                'q3_price_violation_lines_total'):
        value = answers[key]
        if not _is_int(value):
            raise TypeError('{} must be int, got {}'.format(key, type(value).__name__))
        if value < 0:
            raise ValueError('{} must be non-negative'.format(key))

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

    q4 = answers['q4_chats_meeting_before_price']
    if not isinstance(q4, list):
        raise TypeError('q4_chats_meeting_before_price must be a list')
    if any(not isinstance(item, str) or not item.strip() for item in q4):
        raise TypeError('q4_chats_meeting_before_price must contain non-empty strings')
    if q4 != sorted(q4):
        raise ValueError('q4_chats_meeting_before_price must be sorted')

    if not isinstance(answers['run_command'], str) or not answers['run_command'].strip():
        raise ValueError('run_command must be a non-empty string')
    if not isinstance(answers['notes'], str) or not answers['notes'].strip():
        raise ValueError('notes must be a non-empty string')

    return answers
