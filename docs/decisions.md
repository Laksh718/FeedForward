# Decisions

| # | Decision | Why |
|---|---|---|
| 1 | Own git repo inside `FeedForward/` | The home folder is already a repo for other work |
| 2 | Python 3.12 venv | PyTorch CPU wheels are safest there |
| 3 | Ruff rules E, F, I, B, line length 120 | The default rule set is very strict |
| 4 | `nlp_entities.py` separate from `nlp_text.py` | Keeps files under 300 lines, one job each |
| 5 | Spelling map is for matching only; display names keep the catalogue spelling | Briyani and biryani must match, but the screen shows the mess's own name |
| 6 | `!` and `?` are removed by `clean_text` | Stray symbols; sentence splitting runs on raw text |
| 7 | Dish names that collide after normalising stop the pipeline | Silent merging of two dishes would corrupt counts |
| 8 | Missing lag filled with the mean of the other lags (else 0) plus `has_lag_*` and `n_lags` | Keeps inputs free of NaN without peeking at the future. Rows with `n_lags = 0` (first week) are warm up rows |
| 9 | Demand outliers are flagged, not removed | A flagged value may be a real event (festival, exam). Flag uses demand per attendee, robust z score above 4 |
| 10 | `leftover_kg` is recomputed from portion size only for repaired rows | One cleaned row differs by 0.01 kg from the ground truth (rounding) |
| 11 | Regimes: vacation > holiday or festival > university exam > rainy (rain level 2 or more) > normal | Formative test weeks are normal class days. Rainy days are few (84 rows, about 8 days) because most overlap exams |
| 12 | Future calendar: only Deepavali is marked `major_festival` | Matches the real file, where only 4 festivals are major. Other holidays are public holidays |
| 13 | Future exam windows after 2026-11-25 are `estimated`; schedule dates from the SRM notices are `probable` | Official dates are not published yet |
| 14 | Expected attendance is added in M3 (needs out of fold predictions) | Avoids a train versus serve mismatch |
| 15 | Rolling origin folds are the last 4 blocks of 28 days (2026-06-16 to 2026-10-05) | The data ends there; each fold trains only on earlier days |
