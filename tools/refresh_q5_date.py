from datetime import date
from pathlib import Path
import re

from docx import Document


PREFIXES = (
    'AK Furs · итоги сверки данных · ',
    'AK Furs · ответ менеджера · ',
)


def update_markdown(path, today):
    if not path.exists():
        return False
    text = path.read_text(encoding='utf-8')
    updated = re.sub(
        r'(AK Furs · итоги сверки данных · )\d{2}\.\d{2}\.\d{4}',
        r'\g<1>' + today,
        text,
    )
    if updated != text:
        path.write_text(updated, encoding='utf-8')
        return True
    return False


def update_docx(path, today):
    if not path.exists():
        return False
    document = Document(path)
    changed = False
    for paragraph in document.paragraphs:
        for prefix in PREFIXES:
            if paragraph.text.startswith(prefix):
                if paragraph.runs:
                    paragraph.runs[0].text = prefix + today
                    for run in paragraph.runs[1:]:
                        run.text = ''
                changed = True
    if changed:
        document.save(path)
    return changed


def main():
    today = date.today().strftime('%d.%m.%Y')
    targets = [
        Path('Q5.md'),
        Path('Q5.docx'),
        Path('handoff') / 'Q5.md',
        Path('handoff') / 'Q5.docx',
    ]
    for path in targets:
        changed = update_markdown(path, today) if path.suffix == '.md' else update_docx(path, today)
        print('{}: {}'.format(path, 'updated' if changed else 'unchanged'))
    print('date:', today)


if __name__ == '__main__':
    main()
