"""Синхронизация ответа клиентке C0010 в Word с источником Markdown."""

from pathlib import Path

from docx import Document


ROOT = Path(__file__).resolve().parents[1]
HEADING = 'ОТВЕТ КЛИЕНТКЕ В ЧАТЕ C0010'
DATE_PREFIX = 'AK Furs · ответ менеджера · '
NOTE_PREFIX = 'Справочно для проверки перед отправкой:'


def reply_from_markdown(path):
    """Возвращает только клиентские абзацы ответа: без строки даты и служебной сноски."""
    text = Path(path).read_text(encoding='utf-8')
    if HEADING not in text:
        raise ValueError('Q5 client-reply heading not found in {}'.format(path))
    section = text.split(HEADING, 1)[1]
    section = section.split(NOTE_PREFIX, 1)[0]
    reply = [
        line.strip() for line in section.splitlines()
        if line.strip() and not line.strip().startswith(DATE_PREFIX)
    ]
    if not reply:
        raise ValueError('Q5 client reply is empty in {}'.format(path))
    return reply


def _set_paragraph_text(paragraph, text):
    if paragraph.runs:
        paragraph.runs[0].text = text
        for run in paragraph.runs[1:]:
            run.text = ''
    elif text:
        paragraph.add_run(text)


def sync_docx(markdown_path, docx_path):
    reply = reply_from_markdown(markdown_path)
    document = Document(docx_path)
    start = next((index for index, paragraph in enumerate(document.paragraphs)
                  if paragraph.text.startswith(('Здравствуйте!', 'Ответ не сформирован:'))), None)
    if start is None:
        raise ValueError('client reply paragraph not found in {}'.format(docx_path))

    slots = []
    for paragraph in document.paragraphs[start:]:
        if paragraph.text.startswith(NOTE_PREFIX):
            break
        if paragraph.text.strip():
            slots.append(paragraph)
    if len(slots) < len(reply):
        raise ValueError('not enough existing reply paragraphs in {}'.format(docx_path))

    for index, paragraph in enumerate(slots):
        _set_paragraph_text(paragraph, reply[index] if index < len(reply) else '')
    document.save(docx_path)


def main():
    targets = (
        (ROOT / 'Q5.md', ROOT / 'Q5.docx'),
        (ROOT / 'employer_package' / 'Q5.md', ROOT / 'employer_package' / 'Q5.docx'),
    )
    for markdown_path, docx_path in targets:
        if markdown_path.exists() and docx_path.exists():
            sync_docx(markdown_path, docx_path)
            print('updated:', docx_path.relative_to(ROOT))


if __name__ == '__main__':
    main()
