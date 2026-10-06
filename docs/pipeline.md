# Pipeline

Structured around the NLP project phases, extended with the forecasting stages.

| Phase | What happens | Code | Output |
|---|---|---|---|
| 1. Data collection | Read the four dataset folders (read only), validate columns and dates | `data/schemas.py`, `data/loaders.py`, `data/profile.py` | profile printed |
| 2. Preprocessing | Clean text, lower case for matching, tokenise, normalise spelling, map names to ids, unify ids and dates | `data/nlp_text.py`, `data/preprocess.py` | `artifacts/processed/*.parquet`, `reports/nlp_normalisation_report.md` |
| 2b. Cleaning | Drop duplicates, repair missing and negative values, check consistency, flag outliers | `data/cleaning.py` | `kitchen_clean.parquet`, `reports/cleaning_log.json` |
| 3. Feature extraction | Calendar, weather, menu, text (TF-IDF then SVD) and lag features, with a registry | `data/features.py`, `data/text_features.py`, `data/feature_registry.py` | `reports/feature_registry.md` |
| 3b. Time series datasets | Panel, sequence windows, attendance series, day totals, inventory features | `data/timeseries.py`, `data/inventory_features.py` | `artifacts/timeseries/` |
| 4. Model assessment | Chronological splits, rolling origin folds, regimes | `data/splits.py` (M3 adds metrics) | `reports/` |
| 5. Deployment | API, dashboard, copilot (M4 and M5) | `api/`, `app/`, `copilot/` | |
| 6. Feedback | Admin daily log, retraining with real rows (M7) | `admin/` | |

Run order: `python -m feedforward.data.preprocess`, then `data.cleaning`, `data.timeseries`,
`data.inventory_features`. Everything is seeded and regenerable from `Datasets/`.
