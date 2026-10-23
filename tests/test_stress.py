import pytest

from akfurs.io_loaders import load_dataset
from akfurs.report import build_answers, validate
from tools import stress


def answers_for(path):
    return validate(build_answers(load_dataset(path)))


@pytest.fixture(scope='session')
def baseline(data_dir):
    return answers_for(data_dir)


@pytest.mark.parametrize('name', sorted(stress.INVARIANT_VARIANTS))
def test_invariant_variant_matches_baseline(name, data_dir, tmp_path, baseline):
    destination = tmp_path / name
    stress.INVARIANT_VARIANTS[name](data_dir, destination)
    assert answers_for(destination) == baseline


def test_mutation_cover_unpaid_order(data_dir, tmp_path, baseline):
    if not baseline['q2a_paid_orders_without_payment']:
        pytest.skip('the current input has no paid order awaiting a payment')
    destination = tmp_path / 'cover'
    stress.mutation_cover_unpaid_order(data_dir, destination)
    result = answers_for(destination)

    assert 12 in baseline['q2a_paid_orders_without_payment']
    assert 12 not in result['q2a_paid_orders_without_payment']
    assert len(result['q2a_paid_orders_without_payment']) == \
        len(baseline['q2a_paid_orders_without_payment']) - 1
    assert result['q2b_unidentified_payments_count'] == \
        baseline['q2b_unidentified_payments_count']


def test_mutation_add_unidentified_payment(data_dir, tmp_path, baseline):
    destination = tmp_path / 'unidentified'
    stress.mutation_add_unidentified_payment(data_dir, destination)
    result = answers_for(destination)

    assert result['q2b_unidentified_payments_count'] == \
        baseline['q2b_unidentified_payments_count'] + 1
    assert result['q2b_unidentified_payments_sum_rub'] == \
        baseline['q2b_unidentified_payments_sum_rub'] + 100000
    assert result['q2a_paid_orders_without_payment'] == \
        baseline['q2a_paid_orders_without_payment']


def test_mutation_add_cheap_line(data_dir, tmp_path, baseline):
    destination = tmp_path / 'cheap'
    stress.mutation_add_cheap_line(data_dir, destination)
    result = answers_for(destination)

    assert result['q3_price_violation_lines_total'] == \
        baseline['q3_price_violation_lines_total'] + 1
    manager_changes = {
        name: result['q3_price_violation_lines_by_manager'].get(name, 0)
        - baseline['q3_price_violation_lines_by_manager'].get(name, 0)
        for name in (set(result['q3_price_violation_lines_by_manager'])
                     | set(baseline['q3_price_violation_lines_by_manager']))
    }
    assert sorted(count for count in manager_changes.values() if count) == [1]
    assert result['q1_unique_orders'] == baseline['q1_unique_orders']
    assert result['q1_unique_order_lines'] == baseline['q1_unique_order_lines'] + 1
    assert result['q4_chats_meeting_before_price'] == baseline['q4_chats_meeting_before_price']


@pytest.mark.parametrize('name', sorted(stress.BROKEN))
def test_broken_data_fails_loudly(name, data_dir, tmp_path):
    destination = tmp_path / name
    stress.BROKEN[name](data_dir, destination)
    with pytest.raises(ValueError):
        answers_for(destination)
