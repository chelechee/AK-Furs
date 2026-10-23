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


def _run(argv):
    args = list(argv[1:])
    out_path = None
    if '--out' in args:
        index = args.index('--out')
        if index + 1 >= len(args):
            print('--out requires a path', file=sys.stderr)
            return 2
        out_path = args[index + 1]
        del args[index:index + 2]

    if len(args) != 1:
        print('usage: python solve.py <data_dir_or_zip> [--out answers.json]', file=sys.stderr)
        return 2

    with _data_source(args[0]) as data_dir:
        dataset = load_dataset(data_dir)
    answers = validate(build_answers(dataset))
    text = _json_value(answers, indent=2) + '\n'

    if out_path:
        with open(out_path, 'w', encoding='utf-8', newline='\n') as handle:
            handle.write(text)
        digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
        print('OK: {} written ({} bytes, SHA-256 {})'.format(
            out_path, len(text.encode('utf-8')), digest))
    else:
        sys.stdout.write(text)
        print('OK: JSON written to stdout', file=sys.stderr)
    return 0


def main(argv):
    try:
        return _run(argv)
    except Exception as error:
        print('ERROR: {}: {}'.format(type(error).__name__, error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
