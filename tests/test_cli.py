import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_cli_writes_same_answers(data_dir, tmp_path):
    output = tmp_path / 'answers.json'
    result = subprocess.run(
        [sys.executable, str(ROOT / 'solve.py'), str(data_dir), '--out', str(output)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert output.read_bytes() == (ROOT / 'answers.json').read_bytes()
