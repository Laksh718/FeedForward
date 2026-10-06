"""Safe CSV loading with schema validation. Datasets are read only."""

import pandas as pd

from feedforward.data.schemas import TABLES


class SchemaError(ValueError):
    """Raised when a dataset file does not have the expected columns."""


def load_table(name: str) -> pd.DataFrame:
    """Load one dataset by name, check its columns and parse its date columns."""
    if name not in TABLES:
        raise KeyError(f"Unknown table '{name}'. Known tables: {sorted(TABLES)}")
    spec = TABLES[name]
    if not spec.path.exists():
        raise FileNotFoundError(f"Dataset file not found: {spec.path}")
    df = pd.read_csv(spec.path, encoding="utf-8")
    missing = [c for c in spec.columns if c not in df.columns]
    extra = [c for c in df.columns if c not in spec.columns]
    if missing or extra:
        raise SchemaError(f"{spec.path.name}: missing columns {missing}, unexpected {extra}")
    for col in spec.date_cols:
        df[col] = pd.to_datetime(df[col], errors="raise")
    return df


def load_all() -> dict[str, pd.DataFrame]:
    """Load and validate every dataset table."""
    return {name: load_table(name) for name in TABLES}
