"""Проверка Q5: текст соответствует данным, Markdown и Word совпадают."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from docx import Document

from akfurs import q5
from akfurs.io_loaders import load_dataset
from akfurs.replies import check_emoji_policy

DATE = re.compile(r'AK Furs · [^·]+ · (\d{2}\.\d{2}\.\d{4})')


def _normalize(text):
    lines = text.replace('\r\n', '\n').splitlines()
    return '\n'.join(line.rstrip() for line in lines).strip()


def _first_difference(expected, actual):
    expected_lines = expected.splitlines()
    actual_lines = actual.splitlines()
    for index, (left, right) in enumerate(zip(expected_lines, actual_lines), start=1):
        if left != right:
            return index, left, right
    if len(expected_lines) != len(actual_lines):
        return min(len(expected_lines), len(actual_lines)) + 1, '<конец файла>', '<конец файла>'
    return None


def verify(markdown, docx_texts, figures):
    """Сверяет Q5 с данными. Возвращает дату документа, при расхождении бросает ValueError."""
    dates = DATE.findall(markdown)
    if len(dates) != 2:
        raise ValueError('Q5.md must contain two dated lines (memo and client reply), '
                         'found {}'.format(len(dates)))
    if dates[0] != dates[1]:
        raise ValueError('Q5.md dates differ: {} and {}'.format(*dates))

    expected = q5.markdown(figures, dates[0])
    if _normalize(markdown) != _normalize(expected):
        index, wanted, got = _first_difference(expected, markdown)
        raise ValueError(
            'Q5.md does not match the data, run python tools/build_q5.py '
            '(line {}: expected {!r}, found {!r})'.format(index, wanted, got))

    reply = q5.reply_paragraphs(figures, dates[0])[2:]
    check_emoji_policy('\n\n'.join(reply), figures['client']['client_emoji'], brand_emoji=True)

    expected_docx = q5.docx_texts(figures, dates[0])
    if [text.strip() for text in docx_texts] != [text.strip() for text in expected_docx]:
        raise ValueError('Q5.docx does not match the generated text, '
                         'run python tools/build_q5.py')
    return dates[0]


def main():
    try:
        dataset = load_dataset(ROOT / 'data')
        figures = q5.build_figures(dataset)
        output_dir = ROOT / 'handoff'
        if not (output_dir / 'Q5.md').is_file() or not (output_dir / 'Q5.docx').is_file():
            output_dir = ROOT
        markdown = (output_dir / 'Q5.md').read_text(encoding='utf-8')
        paragraphs = [paragraph.text for paragraph in Document(output_dir / 'Q5.docx').paragraphs]
        date = verify(markdown, paragraphs, figures)
    except Exception as error:
        print('ERROR: {}: {}'.format(type(error).__name__, error), file=sys.stderr)
        return 1

    print('OK: Q5 matches data ({}), Markdown and Word; client emoji: {}'.format(
        date, 'yes' if figures['client']['client_emoji'] else 'no'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
