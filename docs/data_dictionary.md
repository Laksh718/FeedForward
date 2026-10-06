# Data dictionary

Data type classes: **structured** (fixed typed columns), **semi structured** (short free text with a
loose pattern), **unstructured** (free text). Real or simulated is stated in the dataset README and repeated
here because it matters for every claim we make.

| Table | Rows | Origin | Structured fields | Semi structured / unstructured fields |
|---|---|---|---|---|
| kitchen_history (and raw) | 15,745 (15,760) | SIMULATED on real menu, calendar, weather | date, ids, quantities, flags, enrolled, attendance, students_present | `dish_name` (semi structured: short name, raw file has case and space faults) |
| calendar_real | 365 | REAL (79 exam days estimated) | date, flags (holiday, rain holiday, exam), week, month | `senior_phase`, `first_year_phase` (semi structured codes), `holiday_name` (semi structured), `event_note` (unstructured sentence) |
| weather_kattankulathur | 365 | REAL, typed from screenshots | temperatures, rain_level | `condition` (semi structured phrase, e.g. Light Rain with Thunder), `data_quality`, `source` (unstructured) |
| dishes | 151 | menu REAL, portion and popularity ESTIMATED | ids, portion_g, popularity_score | `dish_name` |
| weekly_menu | 303 | REAL | day, slot, order, flags | `condition` (always or 2nd_and_4th_wednesday) |
| recipes | 623 | ESTIMATED | qty_g_per_portion | `ingredient` (semi structured name) |
| inventory_* | 25,550 daily rows | SIMULATED, shelf lives ASSUMED | quantities, dates | `ingredient` |
| calendar_future (data_store) | 118 | seeded from SRM schedules | same as calendar_real | `event_note`; `phase_confidence` says how sure each date is |
| admin logs (data_store/admin_logs) | grows daily | REAL entries, `data_source = admin_real` | quantities, dates | admin free text (special day names) |
| copilot questions | live | typed by the user | none | unstructured question text (NLU front end) |

## Targets and key definitions

- **Demand** = `consumed_qty + unmet_qty`. Consumption alone is censored by what was cooked. Dishes with
  `special_limited = 1` (chicken, egg, fruit, ice cream, sweets) run out often, so their consumption is
  strongly censored.
- **Usual plan** = average of the same dish, slot and weekday over the last two weeks, plus 12 percent.
- **Slot attendance** (`attendance`) is constant for all dishes of a date and slot. `students_present` is
  constant for a date.

## Fields we cannot use, and why

| Field | Reason |
|---|---|
| `rainfall_mm_reported` | Always 0 in the source, so dropped in preprocessing. `rain_level` is used. |
| Same day `prepared_qty`, `topup_qty`, `consumed_qty`, `unmet_qty`, `leftover_*`, `attendance`, `students_present` | Not known when the forecast is made (leakage). Only lags of 7 or more days are used. |
| Weather for 2026-02-01 to 2026-02-28 | Unverified copies of March. Kept, flagged `weather_reliable = 0`. |
| 2026-05-23 temperature | Flagged outlier (`temp_outlier = 1`), not an input. |
| Exam end dates | 79 theory exam days are estimates (`phase_confidence = estimated`, feature `phase_confidence_rank`). |

## Caveats on the data

- The history covers one year, so no season repeats. Last October is the only October. Every evaluation
  number is therefore an estimate, and the rolling origin folds are the honest check.
- Future weather is last year's monthly average and always flagged `weather_assumed = 1`.
