import json
from pathlib import Path

from akfurs.report import REQUIRED_KEYS


ROOT = Path(__file__).resolve().parents[1]


def test_answers_file_is_utf8_without_bom_and_has_notes():
    raw = (ROOT / 'answers.json').read_bytes()
    assert not raw.startswith(b'\xef\xbb\xbf')
    text = raw.decode('utf-8')
    assert text.encode('utf-8') == raw

    answers = json.loads(text)
    assert set(answers) == set(REQUIRED_KEYS)
    assert answers['run_command'] == 'python solve.py data/ --out answers.json'
    assert answers['notes'].startswith('Номер заказа')
    assert 'C0010' in answers['notes']
