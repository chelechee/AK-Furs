from pathlib import Path

from docx import Document

from tools.sync_q5_docx import reply_from_markdown


ROOT = Path(__file__).resolve().parents[1]


def _word_reply(docx_path):
    paragraphs = Document(docx_path).paragraphs
    start = next(index for index, paragraph in enumerate(paragraphs)
                 if paragraph.text.startswith(('Здравствуйте!', 'Ответ не сформирован:')))
    return [paragraph.text for paragraph in paragraphs[start:]]


def test_word_reply_matches_markdown_source():
    expected = reply_from_markdown(ROOT / 'Q5.md')
    actual = _word_reply(ROOT / 'Q5.docx')[:len(expected)]
    assert actual == expected


def test_package_word_reply_matches_markdown_source():
    package_docx = ROOT / 'employer_package' / 'Q5.docx'
    if not package_docx.is_file():
        return
    expected = reply_from_markdown(ROOT / 'Q5.md')
    actual = _word_reply(package_docx)[:len(expected)]
    assert actual == expected
    assert not (ROOT / 'employer_package' / 'Q5.md').exists()


def test_reply_text_excludes_date_and_internal_note():
    reply = reply_from_markdown(ROOT / 'Q5.md')
    assert reply
    assert all(not block.startswith('AK Furs · ') for block in reply)
    assert all(not block.startswith('Справочно') for block in reply)
