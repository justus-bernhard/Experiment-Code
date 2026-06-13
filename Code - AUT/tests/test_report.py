import json
import os
from numbers import Number

import pandas as pd

from src import report


DATA_PATH = 'data/product_family_planning_dataset.csv'
EXPECTED_ROW_COUNT = 500
REQUIRED_TOP_KEYS = {'total_records', 'overall', 'by_product_family', 'meta'}
REQUIRED_OVERALL_KEYS = {
    'total_forecast_demand_units',
    'total_actual_demand_units',
    'total_planned_supply_receipts_units',
    'total_units_fulfilled',
    'mean_beginning_inventory_units',
    'mean_ending_inventory_units',
    'forecast_bias_units',
    'fill_rate_pct',
}
REQUIRED_GROUP_KEYS = {
    'product_family',
    'records',
    'total_forecast_demand_units',
    'total_actual_demand_units',
    'total_planned_supply_receipts_units',
    'total_units_fulfilled',
    'mean_beginning_inventory_units',
    'mean_ending_inventory_units',
    'forecast_bias_units',
    'fill_rate_pct',
}
DECIMAL_METRICS = (
    'mean_beginning_inventory_units',
    'mean_ending_inventory_units',
    'fill_rate_pct',
)


def _assert_is_sorted_by_rules(by_product_family):
    expected = sorted(
        by_product_family,
        key=lambda x: (-x['total_actual_demand_units'], x['product_family']),
    )
    assert by_product_family == expected


def _assert_rounded_3(value):
    assert round(float(value), 3) == float(value)


def _assert_json_safe(value):
    assert isinstance(value, (dict, list, str, int, float, bool, type(None)))
    if isinstance(value, dict):
        for key, item in value.items():
            assert isinstance(key, str)
            _assert_json_safe(item)
    elif isinstance(value, list):
        for item in value:
            _assert_json_safe(item)


def test_dataset_public_integrity():
    df = pd.read_csv(DATA_PATH)

    assert len(df) == EXPECTED_ROW_COUNT
    assert (
        df['ending_inventory_units']
        == df['beginning_inventory_units'] + df['planned_supply_receipts_units'] - df['units_fulfilled']
    ).all()
    assert (df[[
        'forecast_demand_units',
        'actual_demand_units',
        'beginning_inventory_units',
        'planned_supply_receipts_units',
        'units_fulfilled',
        'ending_inventory_units',
    ]] >= 0).all().all()
    assert (df['units_fulfilled'] <= df['actual_demand_units']).all()
    assert (
        df['units_fulfilled']
        <= df['beginning_inventory_units'] + df['planned_supply_receipts_units']
    ).all()


def test_generate_report_schema_public():
    df = pd.read_csv(DATA_PATH)
    r = report.generate_report(df)

    assert REQUIRED_TOP_KEYS.issubset(set(r.keys()))
    assert REQUIRED_OVERALL_KEYS.issubset(set(r['overall'].keys()))
    assert isinstance(r['by_product_family'], list)
    assert isinstance(r['meta'], dict)
    assert {'row_count', 'product_families'}.issubset(set(r['meta'].keys()))
    assert r['total_records'] == EXPECTED_ROW_COUNT
    assert r['meta']['row_count'] == EXPECTED_ROW_COUNT

    for group in r['by_product_family']:
        assert REQUIRED_GROUP_KEYS.issubset(set(group.keys()))


def test_report_uses_json_safe_standard_types_public():
    df = pd.read_csv(DATA_PATH)
    r = report.generate_report(df)

    _assert_json_safe(r)
    json.dumps(r)

    for value in r['overall'].values():
        assert isinstance(value, Number)
    for group in r['by_product_family']:
        assert isinstance(group['product_family'], str)
        assert isinstance(group['records'], int)


def test_main_writes_report_public():
    import runpy

    outdir = os.path.join(os.getcwd(), 'outputs')
    if os.path.exists(outdir):
        try:
            os.remove(os.path.join(outdir, 'report.json'))
        except Exception:
            pass

    runpy.run_module('src.main', run_name='__main__')
    assert os.path.exists(os.path.join('outputs', 'report.json'))

    with open(os.path.join('outputs', 'report.json'), 'r', encoding='utf-8') as f:
        data = json.load(f)

    assert REQUIRED_TOP_KEYS.issubset(set(data.keys()))


def test_generate_report_is_deterministic_public():
    df = pd.read_csv(DATA_PATH)

    r1 = report.generate_report(df.copy())
    r2 = report.generate_report(df.copy())

    assert r1 == r2


def test_rounding_rule_public():
    df = pd.read_csv(DATA_PATH)
    r = report.generate_report(df)

    for metric in DECIMAL_METRICS:
        _assert_rounded_3(r['overall'][metric])

    for group in r['by_product_family']:
        for metric in DECIMAL_METRICS:
            _assert_rounded_3(group[metric])


def test_sorting_rule_public_with_tie_break_fixture():
    df = pd.DataFrame(
        {
            'record_id': [1, 2, 3, 4, 5, 6],
            'month': ['2026-01'] * 6,
            'region': ['EMEA'] * 6,
            'product_family': ['Gamma', 'Gamma', 'Beta', 'Beta', 'Alpha', 'Alpha'],
            'forecast_demand_units': [95, 95, 70, 70, 70, 70],
            'actual_demand_units': [100, 100, 60, 60, 60, 60],
            'beginning_inventory_units': [20, 20, 15, 15, 15, 15],
            'planned_supply_receipts_units': [75, 75, 45, 45, 45, 45],
            'units_fulfilled': [90, 90, 55, 55, 55, 55],
            'ending_inventory_units': [5, 5, 5, 5, 5, 5],
        }
    )

    r = report.generate_report(df)
    labels = [x['product_family'] for x in r['by_product_family']]

    assert labels == ['Gamma', 'Alpha', 'Beta']
    _assert_is_sorted_by_rules(r['by_product_family'])


def test_basic_calculations_public_fixture():
    df = pd.DataFrame(
        {
            'record_id': [1, 2],
            'month': ['2026-01', '2026-01'],
            'region': ['EMEA', 'EMEA'],
            'product_family': ['Alpha', 'Alpha'],
            'forecast_demand_units': [100, 120],
            'actual_demand_units': [110, 100],
            'beginning_inventory_units': [30, 40],
            'planned_supply_receipts_units': [80, 70],
            'units_fulfilled': [105, 95],
            'ending_inventory_units': [5, 15],
        }
    )

    r = report.generate_report(df)

    assert r['overall']['total_forecast_demand_units'] == 220
    assert r['overall']['total_actual_demand_units'] == 210
    assert r['overall']['total_planned_supply_receipts_units'] == 150
    assert r['overall']['total_units_fulfilled'] == 200
    assert r['overall']['mean_beginning_inventory_units'] == 35
    assert r['overall']['mean_ending_inventory_units'] == 10
    assert r['overall']['forecast_bias_units'] == -10
    assert r['overall']['fill_rate_pct'] == round(200 / 210 * 100, 3)
