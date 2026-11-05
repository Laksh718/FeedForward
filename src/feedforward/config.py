"""Single source of truth for paths, constants and seeds."""

import os
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
ADMIN_LOG_DIR = Path(os.getenv("FEEDFORWARD_ADMIN_LOG_DIR") or DATA_STORE_DIR / "admin_logs")  # tests point this at a temp folder
CALENDAR_FUTURE_CSV = DATA_STORE_DIR / "calendar_future.csv"

# Reproducibility.
SEED = 42

# Project calendar.
HISTORY_START = "2025-10-06"
HISTORY_END = "2026-10-05"
TODAY = "2026-10-06"            # the project's "today"; override with FEEDFORWARD_TODAY in .env
FORECAST_LAST_DAY = "2027-01-31"  # last date covered by data_store/calendar_future.csv

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

# Conditional VAE settings.
VAE_LATENT, VAE_HIDDEN, VAE_EMB, VAE_DROPOUT = 8, 128, 8, 0.1
VAE_LR, VAE_WEIGHT_DECAY, VAE_BATCH = 1e-3, 1e-5, 256
VAE_EPOCHS, VAE_ANNEAL_EPOCHS, VAE_PATIENCE = 200, 20, 15
VAE_FREE_BITS = 0.2         # nats per latent dimension that cost nothing (guards against posterior collapse)
N_SAMPLES = 500
EXTRA_DATA_WEIGHT = 0.3     # weight of synthetic rows from the GAN (real rows weigh 1)
RECOMMEND_QUANTILE = 0.75   # cook the P75 by default
COVERAGE_TARGET = 0.80      # the P10 to P90 band should contain about 80 percent of outcomes

# Admin daily log
ENROLLED = 4000             # enrolled students: the upper limit for an attendance entry
MIN_REAL_DAYS = 28          # warn when retraining with fewer real days than this
REAL_ROW_WEIGHT = 3.0       # default weight of real (admin) rows when retraining
TEMP_MIN_C, TEMP_MAX_C = 10, 50

# Domain constants.
MEAL_SLOTS = ("breakfast", "lunch", "snacks", "dinner")
USUAL_PLAN_BUFFER = 0.12  # manager rule: recent average plus 12 percent
USUAL_PLAN_WEEKS = 2      # ... of the same dish, slot and weekday over 2 weeks
