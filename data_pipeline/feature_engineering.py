import pandas as pd

def generate_historical_features(df, time_col='timestamp', group_cols=None):
    """
    Generate rolling window features (30s, 60s) for predictive routing.
    """
    if df.empty:
        return df
        
    if group_cols is None:
        group_cols = ['switch_id', 'port_no']
        
    df = df.sort_values(by=[*group_cols, time_col])
    
    # We assume the dataframe is already 5-second windowed.
    # 30 seconds = 6 windows
    # 60 seconds = 12 windows
    
    features = df.copy()
    
    # Example for 'tx_bytes' (utilization proxy)
    if 'tx_bytes' in features.columns:
        features['tx_bytes_rate'] = features.groupby(group_cols)['tx_bytes'].diff().fillna(0)
        
        # 30s rolling
        roll_30s = features.groupby(group_cols)['tx_bytes_rate'].rolling(window=6, min_periods=1)
        features['tx_bytes_mean_30s'] = roll_30s.mean().reset_index(level=group_cols, drop=True)
        features['tx_bytes_max_30s'] = roll_30s.max().reset_index(level=group_cols, drop=True)
        features['tx_bytes_std_30s'] = roll_30s.std().fillna(0).reset_index(level=group_cols, drop=True)
        
        # 60s rolling
        roll_60s = features.groupby(group_cols)['tx_bytes_rate'].rolling(window=12, min_periods=1)
        features['tx_bytes_max_60s'] = roll_60s.max().reset_index(level=group_cols, drop=True)
        
        # Slope (rough approximation over last 30s: (current - prev_6th) / 6)
        features['tx_bytes_slope_30s'] = (features['tx_bytes_rate'] - features.groupby(group_cols)['tx_bytes_rate'].shift(6).fillna(0)) / 6

    # Apply the same logic for other relevant metrics (dropped packets, etc.)
    if 'tx_dropped' in features.columns:
        features['tx_dropped_rate'] = features.groupby(group_cols)['tx_dropped'].diff().fillna(0)
        features['loss_mean_30s'] = features.groupby(group_cols)['tx_dropped_rate'].rolling(window=6, min_periods=1).mean().reset_index(level=group_cols, drop=True)

    return features

if __name__ == "__main__":
    print("Feature engineering module ready.")
