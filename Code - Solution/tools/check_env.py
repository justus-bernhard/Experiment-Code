from pathlib import Path

import numpy as np
import pandas as pd

project_root = Path(__file__).resolve().parents[1]
data_path = project_root / 'data' / 'product_family_planning_dataset.csv'

print('pandas', pd.__version__)
print('numpy', np.__version__)
df = pd.read_csv(data_path)
print('loaded rows,cols:', df.shape)
