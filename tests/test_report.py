import pytest

from akfurs.io_loaders import load_dataset
from akfurs.report import build_answers, validate


def valid_answers():
    return {
        'q1_unique_orders': 10,
        'q1_unique_order_lines': 12,
        'q2a_paid_orders_without_payment': [2, 7],
        'q2b_unidentified_payments_count': 1,
        'q2b_unidentified_payments_sum_rub': 100000,
        'q3_price_violation_lines_total': 3,
        'q3_price_violation_lines_by_manager': {'Марина Котова': 3},
        'q4_chats_meeting_before_price': ['C0001', 'C0002'],
        'run_command': 'python solve.py data/ --out answers.json',
        'notes': 'толкования',
    }


def test_valid_answers_pass_and_are_returned():
    answers = valid_answers()
    assert validate(answers) is answers


def test_missing_key_is_rejected():
    answers = valid_answers()
    del answers['notes']
    with pytest.raises(ValueError) as error:
        validate(answers)
    assert 'notes' in str(error.value)


def test_unexpected_key_is_rejected():
    answers = valid_answers()
    answers['debug'] = True
    with pytest.raises(ValueError) as error:
        validate(answers)
    assert 'debug' in str(error.value)


@pytest.mark.parametrize('key', [
    'q1_unique_orders',
    'q1_unique_order_lines',
    'q2b_unidentified_payments_count',
    'q2b_unidentified_payments_sum_rub',
    'q3_price_violation_lines_total',
])
def test_non_integer_counter_is_rejected(key):
    answers = valid_answers()
    answers[key] = '3'
    with pytest.raises(TypeError) as error:
        validate(answers)
    assert key in str(error.value)


def test_negative_counter_is_rejected():
    answers = valid_answers()
    answers['q1_unique_orders'] = -1
    with pytest.raises(ValueError):
        validate(answers)


def test_manager_breakdown_must_be_dict():
    answers = valid_answers()
    answers['q3_price_violation_lines_by_manager'] = [('Марина Котова', 3)]
    with pytest.raises(TypeError):
        validate(answers)


def test_manager_name_must_be_string():
    answers = valid_answers()
    answers['q3_price_violation_lines_by_manager'] = {1: 3}
    with pytest.raises(TypeError):
        validate(answers)


def test_manager_count_must_be_integer():
    answers = valid_answers()
    answers['q3_price_violation_lines_by_manager'] = {'Марина Котова': '3'}
    with pytest.raises(TypeError):
        validate(answers)


@pytest.mark.parametrize('key', [
    'q2a_paid_orders_without_payment',
    'q4_chats_meeting_before_price',
])
def test_list_field_must_be_list(key):
    answers = valid_answers()
    answers[key] = 'C0001'
    with pytest.raises(TypeError) as error:
        validate(answers)
    assert key in str(error.value)


@pytest.mark.parametrize('key', [
    'q2a_paid_orders_without_payment',
    'q4_chats_meeting_before_price',
])
def test_list_field_must_be_sorted(key):
    answers = valid_answers()
    answers[key] = list(reversed(answers[key]))
    with pytest.raises(ValueError):
        validate(answers)


def test_empty_run_command_is_rejected():
    answers = valid_answers()
    answers['run_command'] = '   '
    with pytest.raises(ValueError):
        validate(answers)


def test_empty_notes_is_rejected():
    answers = valid_answers()
    answers['notes'] = ''
    with pytest.raises(ValueError):
        validate(answers)


def test_real_pipeline_output_satisfies_contract(data_dir):
    answers = build_answers(load_dataset(data_dir))
    assert validate(answers) == answers
    assert answers['q2a_paid_orders_without_payment'] == \
        sorted(answers['q2a_paid_orders_without_payment'])
    assert answers['q4_chats_meeting_before_price'] == \
        sorted(answers['q4_chats_meeting_before_price'])
    assert sum(answers['q3_price_violation_lines_by_manager'].values()) == \
        answers['q3_price_violation_lines_total']
