import hashlib
import json
import sys
import tempfile
import zipfile
from contextlib import contextmanager
from pathlib import Path

from akfurs.io_loaders import load_dataset
from akfurs.report import build_answers, validate


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
    text = json.dumps(answers, ensure_ascii=False, indent=2) + '\n'

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
