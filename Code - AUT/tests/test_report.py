import json
import os

import pandas as pd

from src import report


REQUIRED_TOP_KEYS = {'total_participants', 'overall', 'by_noise', 'meta'}
REQUIRED_OVERALL_KEYS = {
    'mean_focus',
    'median_focus',
    'mean_duration',
    'mean_fatigue',
    'focus_fatigue_gap',
}
REQUIRED_GROUP_KEYS = {
    'background_noise_type',
    'participants',
    'mean_focus',
    'median_focus',
    'mean_duration',
    'mean_fatigue',
    'focus_fatigue_gap',
}

FLOAT_METRICS = (
    'mean_focus',
    'median_focus',
    'mean_duration',
    'mean_fatigue',
    'focus_fatigue_gap',
)


def _assert_is_sorted_by_rules(by_noise):
    expected = sorted(
        by_noise,
        key=lambda x: (-x['mean_focus'], x['background_noise_type']),
    )
    assert by_noise == expected


def _assert_rounded_3(value):
    assert round(float(value), 3) == float(value)


def test_generate_report_schema_public():
    df = pd.read_csv('data/background_noise_focus_dataset.csv')
    r = report.generate_report(df)

    assert REQUIRED_TOP_KEYS.issubset(set(r.keys()))
    assert REQUIRED_OVERALL_KEYS.issubset(set(r['overall'].keys()))
    assert isinstance(r['by_noise'], list)
    assert isinstance(r['meta'], dict)
    assert {'row_count', 'noise_types'}.issubset(set(r['meta'].keys()))

    for group in r['by_noise']:
        assert REQUIRED_GROUP_KEYS.issubset(set(group.keys()))


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
    df = pd.read_csv('data/background_noise_focus_dataset.csv')

    r1 = report.generate_report(df.copy())
    r2 = report.generate_report(df.copy())

    assert r1 == r2


def test_rounding_rule_public():
    df = pd.read_csv('data/background_noise_focus_dataset.csv')
    r = report.generate_report(df)

    for metric in FLOAT_METRICS:
        _assert_rounded_3(r['overall'][metric])

    for group in r['by_noise']:
        for metric in FLOAT_METRICS:
            _assert_rounded_3(group[metric])


def test_sorting_rule_public_with_tie_break_fixture():
    df = pd.DataFrame(
        {
            'participant_id': [1, 2, 3, 4, 5, 6],
            'background_noise_type': ['Gamma', 'Gamma', 'Beta', 'Beta', 'Alpha', 'Alpha'],
            'perceived_focus_score': [8, 10, 1, 5, 2, 4],
            'focus_duration_minutes': [60, 62, 50, 55, 58, 56],
            'mental_fatigue_after_task': [4, 5, 6, 7, 5, 6],
        }
    )

    r = report.generate_report(df)
    labels = [x['background_noise_type'] for x in r['by_noise']]

    assert labels == ['Gamma', 'Alpha', 'Beta']
    _assert_is_sorted_by_rules(r['by_noise'])
