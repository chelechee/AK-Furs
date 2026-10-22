import hashlib
import json
import sys

from akfurs.io_loaders import load_dataset
from akfurs.report import build_answers, validate


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
        print('usage: python solve.py <data_dir> [--out answers.json]', file=sys.stderr)
        return 2

    dataset = load_dataset(args[0])
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
