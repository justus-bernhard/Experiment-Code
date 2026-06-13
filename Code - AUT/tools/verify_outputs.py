from pathlib import Path

import pandas as pd

project_root = Path(__file__).resolve().parents[1]
df = pd.read_csv(project_root / 'data' / 'product_family_planning_dataset.csv')

print('DATA SHAPE:', df.shape)

print('\nDemand and inventory summary:')
for col in [
    'forecast_demand_units',
    'actual_demand_units',
    'beginning_inventory_units',
    'planned_supply_receipts_units',
    'units_fulfilled',
    'ending_inventory_units',
]:
    print(f"{col}: sum={df[col].sum():.0f}, mean={df[col].mean():.3f}")

print('\nGroup by product_family:')
g = df.groupby('product_family').agg(
    records=('record_id', 'count'),
    total_actual_demand_units=('actual_demand_units', 'sum'),
    total_units_fulfilled=('units_fulfilled', 'sum'),
    mean_ending_inventory_units=('ending_inventory_units', 'mean'),
)
print(g)

print('\nStock-flow equation valid:', bool(
    (
        df['ending_inventory_units']
        == df['beginning_inventory_units'] + df['planned_supply_receipts_units'] - df['units_fulfilled']
    ).all()
))
