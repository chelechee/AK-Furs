import pytest
from decimal import Decimal

from akfurs.io_loaders import load_dataset
from akfurs.report import build_answers, validate
from solve import _json_value


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


def test_boolean_counter_is_rejected():
    answers = valid_answers()
    answers['q1_unique_orders'] = True
    with pytest.raises(TypeError):
        validate(answers)


def test_q2a_elements_must_be_integers():
    answers = valid_answers()
    answers['q2a_paid_orders_without_payment'] = [2, '7']
    with pytest.raises(TypeError):
        validate(answers)


def test_q2a_elements_must_be_non_negative():
    answers = valid_answers()
    answers['q2a_paid_orders_without_payment'] = [-1, 2]
    with pytest.raises(ValueError):
        validate(answers)


def test_q4_elements_must_be_non_empty_strings():
    answers = valid_answers()
    answers['q4_chats_meeting_before_price'] = ['C0001', '']
    with pytest.raises(TypeError):
        validate(answers)


def test_q4_elements_must_be_strings():
    answers = valid_answers()
    answers['q4_chats_meeting_before_price'] = ['C0001', 2]
    with pytest.raises(TypeError):
        validate(answers)


def test_q3_counts_must_be_non_negative():
    answers = valid_answers()
    answers['q3_price_violation_lines_by_manager'] = {'Марина Котова': -1}
    with pytest.raises(ValueError):
        validate(answers)


def test_q3_manager_name_must_be_non_empty():
    answers = valid_answers()
    answers['q3_price_violation_lines_by_manager'] = {'   ': 3}
    with pytest.raises(ValueError):
        validate(answers)


def test_q3_total_must_match_breakdown():
    answers = valid_answers()
    answers['q3_price_violation_lines_total'] = 4
    with pytest.raises(ValueError):
        validate(answers)


def test_fractional_payment_sum_is_preserved_as_exact_json_number(data_dir):
    import json
    dataset = load_dataset(data_dir)
    dataset['bank'].append({
        'date_raw': '01.10.2026',
        'time_raw': '12:00',
        'amount_raw': '1,49',
        'currency': 'RUR',
        'kind': 'Поступление',
        'counterparty': 'synthetic',
        'purpose': 'payment without any CRM order reference',
    })
    answers = validate(build_answers(dataset))
    assert answers['q2b_unidentified_payments_sum_rub'] == Decimal('3437101.49')
    serialized = _json_value(answers)
    decoded = json.loads(serialized, parse_float=Decimal)
    assert decoded['q2b_unidentified_payments_sum_rub'] == Decimal('3437101.49')


def test_validator_rejects_non_finite_payment_sum():
    answers = valid_answers()
    answers['q2b_unidentified_payments_sum_rub'] = Decimal('NaN')
    with pytest.raises(ValueError, match='finite'):
        validate(answers)


def test_validator_rejects_duplicate_result_ids():
    answers = valid_answers()
    answers['q2a_paid_orders_without_payment'] = [2, 2]
    with pytest.raises(ValueError, match='must be unique'):
        validate(answers)

    answers = valid_answers()
    answers['q4_chats_meeting_before_price'] = ['C0001', 'C0001']
    with pytest.raises(ValueError, match='must be unique'):
        validate(answers)
