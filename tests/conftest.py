import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(scope='session')
def data_dir():
    directory = ROOT / 'data'
    if not (directory / '01_crm_orders_export.csv').exists():
        pytest.skip('raw data is not available')
    return directory
