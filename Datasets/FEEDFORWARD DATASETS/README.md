# FEEDFORWARD DATASETS

Data for the FeedForward food demand forecasting project (SRMIST Hostel Mess, 6 Oct 2025 to 5 Oct 2026, about 3,500 students eating per normal class day).
The four folders match the Data Inputs block of the architecture diagram.

**Join keys:** `date` (history, calendar, weather, inventory daily), `dish_id` (history, dishes, recipes, weekly menu), `ingredient` (recipes, inventory).
**Model target for demand:** `consumed_qty + unmet_qty` in kitchen_history.csv.

## Historical Kitchen Data

| File | Rows | What it is | Real or simulated |
|---|---|---|---|
| `kitchen_history.csv` | 15745 | CLEAN history: one row per date x meal x dish with attendance, prepared, top up, consumed, unmet, leftover | SIMULATED on the real menu, calendar and weather |
| `kitchen_history_raw.csv` | 15760 | Same data with injected faults (missing values, duplicates, bad names, negatives) for the preprocessing step | SIMULATED |
| `raw_quality_report.json` | n/a | Count of each fault injected into the raw file | documentation |

## Calendar & Events

| File | Rows | What it is | Real or simulated |
|---|---|---|---|
| `calendar_real.csv` | 365 | Daily calendar: SRM academic phases for two cohorts, TN holidays, festivals, rain holidays, exam flags | REAL (79 theory exam days estimated) |
| `calendar_sources.csv` | 8 | Source behind every calendar and weather fact | documentation |
| `weather_kattankulathur.csv` | 365 | Daily high, low, condition and rain level for the Chennai area | REAL, typed from screenshots (see notes) |

## Menu & Recipe Data

| File | Rows | What it is | Real or simulated |
|---|---|---|---|
| `weekly_menu.csv` | 303 | What is served by day and meal slot, including choice groups and the 2nd/4th Wednesday briyani | REAL menu |
| `dishes.csv` | 151 | Dish catalogue: category, diet, serving size (portion_g), popularity score, core or support | menu REAL, serving size and popularity ESTIMATED |
| `recipes.csv` | 623 | Raw ingredient grams per portion for every dish | ESTIMATED |

## Inventory Data

| File | Rows | What it is | Real or simulated |
|---|---|---|---|
| `inventory_batches.csv` | 2391 | One row per ingredient per 10 day delivery: quantity, shelf life, expiry date, used, expired | SIMULATED |
| `inventory_daily.csv` | 25550 | Daily ledger per ingredient: opening, delivered, used, expired, emergency purchase, closing, days to expiry | SIMULATED |
| `inventory_ingredients.csv` | 70 | Ingredient master: storage type, shelf life, pack size, average daily use | shelf lives ASSUMED |

## Notes on the weather file

- Typed by hand from 13 screenshots of a weather calendar website. Spot check a few days against the site.
- **Rainfall in mm is not usable.** The source shows 0 mm on almost every day, including rain and thunder days, so `rainfall_mm_reported` must be ignored. Use `rain_level` (0 none, 1 light, 2 moderate or thunder, 3 heavy), derived from the condition text.
- `rain_level` for 30 Nov to 3 Dec 2025 is raised from news reports of Cyclone Ditwah (the site shows only light rain on those days). See `rain_level_basis`.
- **February 2026 is UNVERIFIED.** The February screenshot was a duplicate of March, so those 28 rows are copies of March (see `data_quality`). Replace when a correct February view is available.
- One day (23 May 2026) is flagged as a temperature outlier to verify.
- `temp_mean_c` is (high + low) / 2.

## Other notes

- Files were copied from the generator workspace `feedforward_data/`, which keeps the scripts that produce them.
- Describe the history and inventory as simulated on a real menu, calendar and weather.
