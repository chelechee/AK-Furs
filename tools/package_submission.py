"""Сборка комплекта для письма работодателю из проверенных материалов.

Комплект лежит в `employer_package/` и в Git не входит: там только то, что
уходит в письме. Результат расчёта остаётся в `handoff/`.
"""

import json
import shutil
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from akfurs.report import validate
from solve import _json_value
from tools.refresh_q5_date import update_docx
from tools.sync_q5_docx import sync_docx

HANDOFF = ROOT / 'handoff'
PACKAGE = ROOT / 'employer_package'

LETTER_FILES = ('примеры-ошибок-агента.md',)
SCREENSHOTS_DIR = 'скриншоты'
SCREENSHOTS_ARCHIVE = 'скриншоты.zip'
ALLOWED_NAMES = frozenset({
    'answers.json', 'README.md', 'Q5.docx', 'примеры-ошибок-агента.md',
})
ALLOWED_IMAGE_SUFFIXES = frozenset({'.jpg', '.jpeg', '.png', '.webp'})


def _check_letter_materials():
    missing = [name for name in LETTER_FILES if not (PACKAGE / name).is_file()]
    has_screens = (PACKAGE / SCREENSHOTS_DIR).is_dir() or (PACKAGE / SCREENSHOTS_ARCHIVE).is_file()
    if not has_screens:
        missing.append(SCREENSHOTS_DIR)
    if missing:
        raise FileNotFoundError('employer_package is missing: {}'.format(', '.join(missing)))


def _check_no_raw_inputs():
    found = []
    for path in PACKAGE.rglob('*'):
        if not path.is_file():
            continue
        if path.name in ALLOWED_NAMES or path.suffix.lower() in ALLOWED_IMAGE_SUFFIXES:
            continue
        found.append(str(path.relative_to(PACKAGE)))
    if found:
        raise ValueError('employer_package must not contain raw inputs: {}'.format(
            ', '.join(found)))


def _answers_text():
    answers_path = HANDOFF / 'answers.json'
    if not answers_path.is_file():
        raise FileNotFoundError('run `python solve.py` first to create handoff/answers.json')
    answers = json.loads(answers_path.read_text(encoding='utf-8'))
    validate(answers)
    return _json_value(answers, indent=2) + '\n'


def build_package():
    _check_letter_materials()
    text = _answers_text()
    (PACKAGE / 'answers.json').write_text(text, encoding='utf-8', newline='\n')

    markdown = HANDOFF / 'Q5.md'
    docx = HANDOFF / 'Q5.docx'
    if not markdown.is_file() or not docx.is_file():
        markdown = ROOT / 'Q5.md'
        docx = ROOT / 'Q5.docx'
    for source in (markdown, docx):
        if not source.is_file():
            raise FileNotFoundError('{} not found in the project root'.format(source.name))
    shutil.copyfile(docx, PACKAGE / 'Q5.docx')

    today = date.today().strftime('%d.%m.%Y')
    update_docx(PACKAGE / 'Q5.docx', today)
    sync_docx(markdown, PACKAGE / 'Q5.docx')

    _check_no_raw_inputs()
    return json.loads(text)


def main():
    try:
        answers = build_package()
    except Exception as error:
        print('ERROR: {}: {}'.format(type(error).__name__, error), file=sys.stderr)
        return 1
    print('OK: employer_package assembled (answers, Q5.docx, letter materials)')
    print('Q4 in answers: {} chats; current Q5 is included in handoff'.format(
        len(answers['q4_chats_meeting_before_price'])))
    markdown = HANDOFF / 'Q5.md'
    if markdown.is_file() and 'Ответ не сформирован' in markdown.read_text(encoding='utf-8'):
        print('WARNING: C0010 is absent; package is a draft and must not be sent to the client')
    return 0


if __name__ == '__main__':
    sys.exit(main())
