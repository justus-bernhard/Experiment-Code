import pandas as pd
import numpy as np
print('pandas', pd.__version__)
print('numpy', np.__version__)
df = pd.read_csv('background_noise_focus_dataset.csv')
print('loaded rows,cols:', df.shape)
