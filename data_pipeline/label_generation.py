import pandas as pd


def generate_sla_labels(df, group_cols=None, horizon_windows=6, loss_threshold=10):
    """
    Generate target labels y_t for predicting SLA violations in the next H windows.
    H = 6 windows (30 seconds at 5s per window).
    """
    if df.empty:
        return df
        
    if group_cols is None:
        group_cols = ['switch_id', 'port_no']
        
    labeled = df.copy()
    
    # We define an SLA violation here loosely as tx_dropped_rate exceeding a threshold
    # In a real scenario, this would be tied to the specific traffic class definitions.
    if 'tx_dropped_rate' not in labeled.columns:
        labeled['tx_dropped_rate'] = labeled.groupby(group_cols).get('tx_dropped', pd.Series()).diff().fillna(0)
        
    labeled['is_violation_now'] = (labeled['tx_dropped_rate'] > loss_threshold).astype(int)
    
    # Check if any violation occurs in the next H windows
    # We use a rolling max backwards (shift + rolling max, or reversing the series)
    
    # Reverse the dataframe within groups to look "forward" using rolling
    def forward_looking_violation(group):
        # Reverse, rolling max over horizon, reverse back
        return group[::-1].rolling(window=horizon_windows, min_periods=1).max()[::-1]
        
    labeled['sla_violated_in_horizon'] = labeled.groupby(group_cols)['is_violation_now'].transform(forward_looking_violation)
    
    return labeled

if __name__ == "__main__":
    print("Label generation module ready.")
