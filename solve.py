import hashlib
import json
import sys
import tempfile
import zipfile
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path

from akfurs.io_loaders import load_dataset
from akfurs.report import build_answers, validate

DEFAULT_SOURCE = Path('data')
DEFAULT_OUTPUT = Path('handoff') / 'answers.json'


def _json_value(value, level=0, indent=2):
    """Serialize Decimal as an exact JSON number without converting via float."""
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError('non-finite Decimal cannot be written to JSON')
        if value == value.to_integral_value():
            return str(int(value))
        text = format(value, 'f')
        return text.rstrip('0').rstrip('.') if '.' in text else text
    if isinstance(value, dict):
        if not value:
            return '{}'
        pad = ' ' * (indent * (level + 1))
        close_pad = ' ' * (indent * level)
        entries = [pad + json.dumps(key, ensure_ascii=False) + ': '
                   + _json_value(item, level + 1, indent)
                   for key, item in value.items()]
        return '{\n' + ',\n'.join(entries) + '\n' + close_pad + '}'
    if isinstance(value, (list, tuple)):
        if not value:
            return '[]'
        pad = ' ' * (indent * (level + 1))
        close_pad = ' ' * (indent * level)
        entries = [pad + _json_value(item, level + 1, indent) for item in value]
        return '[\n' + ',\n'.join(entries) + '\n' + close_pad + ']'
    return json.dumps(value, ensure_ascii=False)


@contextmanager
def _data_source(path):
    source = Path(path)
    if source.is_file() and zipfile.is_zipfile(source):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            with zipfile.ZipFile(source) as archive:
                for member in archive.infolist():
                    target = (base / member.filename).resolve()
                    if target != base and base not in target.parents:
                        raise ValueError('unsafe archive member: {}'.format(member.filename))
                archive.extractall(temporary)
            yield Path(temporary)
        return
    yield source


def _parse_args(argv):
    args = list(argv[1:])
    out_path = DEFAULT_OUTPUT
    if '--out' in args:
        index = args.index('--out')
        if index + 1 >= len(args):
            raise SystemExit('--out requires a path')
        out_path = Path(args[index + 1])
        del args[index:index + 2]

    if len(args) > 1:
        raise SystemExit('usage: python solve.py [data_dir_or_zip] [--out handoff/answers.json]')
    source = Path(args[0]) if args else DEFAULT_SOURCE
    return source, out_path


def _run(argv):
    try:
        source, out_path = _parse_args(argv)
    except SystemExit as error:
        print(error, file=sys.stderr)
        return 2

    with _data_source(source) as data_dir:
        dataset = load_dataset(data_dir)
    answers = validate(build_answers(dataset))
    from tools.build_q5 import render_q5, write_q5

    _, q5_markdown, q5_docx = render_q5(dataset)
    text = _json_value(answers, indent=2) + '\n'

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    q5_markdown_path = out_path.parent / 'Q5.md'
    q5_docx_path = out_path.parent / 'Q5.docx'
    with open(out_path, 'w', encoding='utf-8', newline='\n') as handle:
        handle.write(text)
    write_q5(q5_markdown_path, q5_docx_path, q5_markdown, q5_docx)
    digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
    print('OK: {} written with Q5.md and Q5.docx ({} bytes, SHA-256 {})'.format(
        out_path, len(text.encode('utf-8')), digest))
    return 0


def main(argv):
    try:
        return _run(argv)
    except Exception as error:
        print('ERROR: {}: {}'.format(type(error).__name__, error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
