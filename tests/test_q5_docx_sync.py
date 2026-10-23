from pathlib import Path

from docx import Document

from tools.sync_q5_docx import _reply_from_markdown


ROOT = Path(__file__).resolve().parents[1]


def test_word_replies_match_markdown_source():
    for markdown_path, docx_path in (
        (ROOT / 'Q5.md', ROOT / 'Q5.docx'),
        (ROOT / 'handoff' / 'Q5.md', ROOT / 'handoff' / 'Q5.docx'),
    ):
        expected = _reply_from_markdown(markdown_path)
        paragraphs = Document(docx_path).paragraphs
        start = next(index for index, paragraph in enumerate(paragraphs)
                     if paragraph.text.startswith('Здравствуйте!'))
        actual = [paragraph.text for paragraph in paragraphs[start:start + len(expected)]]
        assert actual == expected
