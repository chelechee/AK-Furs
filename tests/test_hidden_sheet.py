import shutil

import openpyxl

from akfurs.io_loaders import _column, _index_map, _sheet_with_cells, load_dataset
from akfurs.normalize import STATUS_CANCELLED
from akfurs.orders import build_clean_lines
from akfurs.pricing import build_history, minimum_price, solve_q3


def _as_date(value):
    return value.date() if hasattr(value, 'date') else value


def test_changing_hidden_sheet_minimum_changes_q3(data_dir, tmp_path):
    data_copy = tmp_path / 'data'
    shutil.copytree(data_dir, data_copy)

    dataset = load_dataset(data_copy)
    periods = build_history(dataset['pricebook']['history'])
    lines = build_clean_lines(dataset['pricebook'], dataset['crm'])
    before_total, _ = solve_q3(lines, periods)

    target = next(
        line for line in lines
        if line.status != STATUS_CANCELLED
        and line.unit_after < minimum_price(periods, line.article, line.created)
    )

    path = data_copy / '03_catalog_prices_reference.xlsx'
    workbook = openpyxl.load_workbook(path)
    sheet, header_row = _sheet_with_cells(
        workbook, ('Артикул', 'Действует с', 'Действует по'))
    positions = _index_map(sheet, header_row)
    article_at = _column(positions, 'Артикул')
    from_at = _column(positions, 'Действует с')
    to_at = _column(positions, 'Действует по')
    minimum_at = _column(positions, 'Минимально допустимая цена')

    changed = 0
    for row in sheet.iter_rows(min_row=header_row + 1):
        if str(row[article_at].value).strip() != target.article:
            continue
        if _as_date(row[from_at].value) > target.created:
            continue
        if row[to_at].value is not None and _as_date(row[to_at].value) < target.created:
            continue
        row[minimum_at].value = float(target.unit_after)
        changed += 1
    assert changed == 1
    workbook.save(path)

    after_dataset = load_dataset(data_copy)
    after_periods = build_history(after_dataset['pricebook']['history'])
    after_lines = build_clean_lines(after_dataset['pricebook'], after_dataset['crm'])
    after_total, _ = solve_q3(after_lines, after_periods)

    assert after_total < before_total
    assert minimum_price(after_periods, target.article, target.created) >= target.unit_after
