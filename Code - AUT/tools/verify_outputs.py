import pandas as pd

df = pd.read_csv('background_noise_focus_dataset.csv')

print('DATA SHAPE:', df.shape)

# numeric summary
nums = df.select_dtypes(include=['number'])
desc = nums.describe().T
print('\nNumeric summary (count, mean, 50%):')
for col in ['participant_id','age','noise_volume_level','focus_duration_minutes','perceived_focus_score','task_completion_quality','mental_fatigue_after_task']:
    row = desc.loc[col]
    print(f"{col}: count={row['count']}, mean={row['mean']:.6f}, 50%={row['50%']}")

# group stats by background_noise_type
g = df.groupby('background_noise_type').agg(participants=('participant_id','count'), mean_focus=('perceived_focus_score','mean'), median_focus=('perceived_focus_score','median'), mean_duration=('focus_duration_minutes','mean'), mean_fatigue=('mental_fatigue_after_task','mean'))
print('\nGroup by background_noise_type:')
print(g)

# correlation
print('\nCorrelation matrix (selected entries):')
print(nums.corr().round(6))
