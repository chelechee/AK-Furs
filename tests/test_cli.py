import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from akfurs.io_loaders import load_dataset
from akfurs.report import build_answers, validate
from solve import _json_value


ROOT = Path(__file__).resolve().parents[1]


def _expected_answers(data_dir):
    return (_json_value(validate(build_answers(load_dataset(data_dir)))) + '\n').encode('utf-8')


def _run_cli(path, output):
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    return subprocess.run(
        [sys.executable, str(ROOT / 'solve.py'), str(path), '--out', str(output)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding='utf-8',
        env=env,
    )


def _run_default_cli(cwd):
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    return subprocess.run(
        [sys.executable, str(ROOT / 'solve.py')],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding='utf-8',
        env=env,
    )


def test_cli_writes_same_answers(data_dir, tmp_path):
    output = tmp_path / 'answers.json'
    result = _run_cli(data_dir, output)
    assert result.returncode == 0, result.stderr
    assert 'OK:' in result.stdout
    assert 'SHA-256' in result.stdout
    assert output.read_bytes() == _expected_answers(data_dir)
    assert (tmp_path / 'Q5.md').is_file()
    assert (tmp_path / 'Q5.docx').is_file()


def test_cli_finds_nested_data_dir(data_dir, tmp_path):
    nested = tmp_path / 'archive' / 'dataset'
    shutil.copytree(data_dir, nested)
    output = tmp_path / 'answers.json'
    result = _run_cli(tmp_path / 'archive', output)
    assert result.returncode == 0, result.stderr
    assert output.read_bytes() == _expected_answers(data_dir)


def test_cli_accepts_zip(data_dir, tmp_path):
    archive = tmp_path / 'dataset.zip'
    with zipfile.ZipFile(archive, 'w') as handle:
        for path in data_dir.iterdir():
            if path.is_file():
                handle.write(path, 'dataset/' + path.name)
    output = tmp_path / 'answers.json'
    result = _run_cli(archive, output)
    assert result.returncode == 0, result.stderr
    assert output.read_bytes() == _expected_answers(data_dir)


def test_cli_accepts_zip_with_cyrillic_path_and_spaces(data_dir, tmp_path):
    archive = tmp_path / 'Новая выгрузка за октябрь.zip'
    with zipfile.ZipFile(archive, 'w') as handle:
        for path in data_dir.iterdir():
            if path.is_file():
                handle.write(path, 'вложенная папка/выгрузка/' + path.name)
    output = tmp_path / 'Результаты расчёта' / 'answers.json'
    result = _run_cli(archive, output)
    assert result.returncode == 0, result.stderr
    assert 'SHA-256' in result.stdout
    assert output.read_bytes() == _expected_answers(data_dir)


def test_cli_runs_from_cyrillic_path_with_spaces(data_dir, tmp_path):
    project = tmp_path / 'Мои проекты' / 'Ателье АК Фурс'
    project.mkdir(parents=True)
    shutil.copyfile(ROOT / 'solve.py', project / 'solve.py')
    shutil.copytree(ROOT / 'akfurs', project / 'akfurs')
    shutil.copytree(ROOT / 'tools', project / 'tools', ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copytree(data_dir, project / 'data')

    result = subprocess.run(
        [sys.executable, 'solve.py'],
        cwd=str(project),
        capture_output=True,
        text=True,
        encoding='utf-8',
        env={**os.environ, 'PYTHONIOENCODING': 'utf-8'},
    )
    assert result.returncode == 0, result.stderr
    output = project / 'handoff' / 'answers.json'
    assert output.is_file()
    assert output.read_bytes() == _expected_answers(project / 'data')
    assert 'OK: handoff' in result.stdout
    assert 'answers.json' in result.stdout


def test_cli_default_run_writes_only_answers_json(data_dir, tmp_path):
    shutil.copytree(data_dir, tmp_path / 'data')
    result = _run_default_cli(tmp_path)
    assert result.returncode == 0, result.stderr

    output = tmp_path / 'handoff' / 'answers.json'
    assert output.read_bytes() == _expected_answers(tmp_path / 'data')
    assert {path.name for path in (tmp_path / 'handoff').iterdir()} == {
        'answers.json', 'Q5.md', 'Q5.docx'}
    assert result.stdout.strip().count('OK:') == 1


def test_cli_reports_errors(tmp_path):
    output = tmp_path / 'answers.json'
    result = _run_cli(tmp_path / 'missing', output)
    assert result.returncode == 1
    assert 'ERROR:' in result.stderr
    assert 'NotADirectoryError' in result.stderr
    assert not output.exists()
