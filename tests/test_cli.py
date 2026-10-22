import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _run_cli(path, output):
    return subprocess.run(
        [sys.executable, str(ROOT / 'solve.py'), str(path), '--out', str(output)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def test_cli_writes_same_answers(data_dir, tmp_path):
    output = tmp_path / 'answers.json'
    result = _run_cli(data_dir, output)
    assert result.returncode == 0, result.stderr
    assert 'OK:' in result.stdout
    assert 'SHA-256' in result.stdout
    assert output.read_bytes() == (ROOT / 'answers.json').read_bytes()


def test_cli_finds_nested_data_dir(data_dir, tmp_path):
    nested = tmp_path / 'archive' / 'dataset'
    shutil.copytree(data_dir, nested)
    output = tmp_path / 'answers.json'
    result = _run_cli(tmp_path / 'archive', output)
    assert result.returncode == 0, result.stderr
    assert output.read_bytes() == (ROOT / 'answers.json').read_bytes()


def test_cli_accepts_zip(data_dir, tmp_path):
    archive = tmp_path / 'dataset.zip'
    with zipfile.ZipFile(archive, 'w') as handle:
        for path in data_dir.iterdir():
            if path.is_file():
                handle.write(path, 'dataset/' + path.name)
    output = tmp_path / 'answers.json'
    result = _run_cli(archive, output)
    assert result.returncode == 0, result.stderr
    assert output.read_bytes() == (ROOT / 'answers.json').read_bytes()


def test_cli_reports_errors(tmp_path):
    output = tmp_path / 'answers.json'
    result = _run_cli(tmp_path / 'missing', output)
    assert result.returncode == 1
    assert 'ERROR:' in result.stderr
    assert 'NotADirectoryError' in result.stderr
    assert not output.exists()
