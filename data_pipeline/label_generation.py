import pandas as pd


def compute_future_violation_series(series: pd.Series, horizon_steps: int = 15) -> pd.Series:
    """
    Compute future violation looking ahead horizon_steps using a backward rolling window
    and a shift(-1) so that the current timestep's label reflects the future horizon [t+1, t+H].
    Rows without a full horizon receive NaN.
    """
    return (
        series.iloc[::-1]
        .rolling(horizon_steps, min_periods=horizon_steps)
        .max()
        .iloc[::-1]
        .shift(-1)
    )


def generate_future_labels(
    df: pd.DataFrame,
    group_col: str = "experiment_id",
    target_col: str = "current_sla_violated",
    horizon_steps: int = 15
) -> pd.DataFrame:
    """
    Computes sla_violated_in_horizon using groupby.transform to maintain exact DataFrame
    dimensions and prevent column loss or deprecation warnings across Pandas versions.
    """
    if df.empty:
        return df

    labeled = df.copy()
    labeled["sla_violated_in_horizon"] = labeled.groupby(group_col)[target_col].transform(
        lambda s: compute_future_violation_series(s, horizon_steps=horizon_steps)
    )
    return labeled
