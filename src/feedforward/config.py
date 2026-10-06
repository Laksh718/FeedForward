"""Single source of truth for paths, constants and seeds."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Read-only dataset folders (never write inside Datasets/).
DATASET_ROOT = PROJECT_ROOT / "Datasets" / "FEEDFORWARD DATASETS"
CALENDAR_DIR = DATASET_ROOT / "Calendar & Events"
KITCHEN_DIR = DATASET_ROOT / "Historical Kitchen Data"
INVENTORY_DIR = DATASET_ROOT / "Inventory Data"
MENU_DIR = DATASET_ROOT / "Menu & Recipe Data"

# Output folders (all regenerable, except data_store).
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"
PROCESSED_DIR = ARTIFACTS_DIR / "processed"
TIMESERIES_DIR = ARTIFACTS_DIR / "timeseries"
MODELS_DIR = ARTIFACTS_DIR / "models"
NLTK_DATA_DIR = ARTIFACTS_DIR / "nltk_data"
REPORTS_DIR = PROJECT_ROOT / "reports"
DATA_STORE_DIR = PROJECT_ROOT / "data_store"
ADMIN_LOG_DIR = DATA_STORE_DIR / "admin_logs"
CALENDAR_FUTURE_CSV = DATA_STORE_DIR / "calendar_future.csv"

# Reproducibility.
SEED = 42

# Project calendar.
HISTORY_START = "2025-10-06"
HISTORY_END = "2026-10-05"
TODAY = "2026-10-06"

# Chronological splits (inclusive dates).
TRAIN_END = "2026-06-17"
VAL_START, VAL_END = "2026-06-18", "2026-08-11"
TEST_START, TEST_END = "2026-08-12", "2026-10-05"

# Text matching confidence (rapidfuzz score, 0 to 100).
FUZZY_ACCEPT = 90.0   # accept silently
FUZZY_REVIEW = 75.0   # accept but put on the review list

N_FOLDS, FOLD_DAYS = 4, 28   # rolling origin evaluation
SEQ_LOOKBACK = 21            # days of history in each sequence window
DISH_TEXT_DIM = 8    # size of the TF-IDF + SVD dish text embedding

# Domain constants.
MEAL_SLOTS = ("breakfast", "lunch", "snacks", "dinner")
USUAL_PLAN_BUFFER = 0.12  # manager rule: recent average plus 12 percent
USUAL_PLAN_WEEKS = 2      # ... of the same dish, slot and weekday over 2 weeks
