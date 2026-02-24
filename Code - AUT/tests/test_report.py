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


def test_generate_report_schema_public():
    df = pd.read_csv('data/background_noise_focus_dataset.csv')
    r = report.generate_report(df)

    assert REQUIRED_TOP_KEYS.issubset(set(r.keys()))
    assert REQUIRED_OVERALL_KEYS.issubset(set(r['overall'].keys()))
    assert isinstance(r['by_noise'], list)
    assert isinstance(r['meta'], dict)
    assert {'row_count', 'noise_types'}.issubset(set(r['meta'].keys()))

    if r['by_noise']:
        assert REQUIRED_GROUP_KEYS.issubset(set(r['by_noise'][0].keys()))


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
