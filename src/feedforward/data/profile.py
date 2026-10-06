"""Quick profile of every dataset: shape, date range, missing values, duplicates."""

import pandas as pd

from feedforward.data.loaders import load_all


def profile_table(name: str, df: pd.DataFrame) -> str:
    """Return a short text profile of one table."""
    lines = [f"== {name}: {len(df)} rows x {df.shape[1]} columns"]
    date_cols = [c for c in df.columns if pd.api.types.is_datetime64_any_dtype(df[c])]
    for col in date_cols:
        lines.append(f"   {col}: {df[col].min().date()} to {df[col].max().date()}")
    missing = df.isna().sum()
    missing = missing[missing > 0]
    if len(missing):
        lines.append("   missing values: " + ", ".join(f"{k}={v}" for k, v in missing.items()))
    lines.append(f"   exact duplicate rows: {int(df.duplicated().sum())}")
    return "\n".join(lines)


def main() -> None:
    """Print the profile of all datasets."""
    for name, df in load_all().items():
        print(profile_table(name, df))


if __name__ == "__main__":
    main()
