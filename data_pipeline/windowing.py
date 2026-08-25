import pandas as pd
import numpy as np

def create_windows(df, window_size='5s', time_col='timestamp'):
    """
    Resample raw telemetry into fixed-size time windows.
    """
    if df.empty:
        return df
        
    df[time_col] = pd.to_datetime(df[time_col])
    df = df.set_index(time_col)
    
    # Group by switch and port, then resample
    # For numeric columns, take the mean. For byte counts, we can take the diff to get rates.
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    
    # Resample
    windowed = df.groupby(['switch_id', 'port_no']).resample(window_size)[numeric_cols].mean().reset_index()
    
    # Forward fill missing values for continuity in the window
    windowed = windowed.ffill()
    
    return windowed

if __name__ == "__main__":
    print("Windowing module ready.")
