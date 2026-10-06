# Admin log schemas

Real entries saved by the Daily log. Files live in `data_store/admin_logs/` (git ignored) and are written by `CsvLogStore`
(`src/feedforward/admin/store.py`). Column names mirror the dataset tables so the logs can be appended to the history later.

Every table also has these columns:

| Column | Meaning |
|---|---|
| data_source | always `admin_real`; simulated rows are `history_simulated` once combined |
| entered_at | when the row was saved (ISO time) |
| entered_by | optional name of the person who entered it |
| deleted | 0 normally, 1 after a soft delete (the row stays in the file and is ignored everywhere) |

Saving a date again updates its rows. Rows of that date that are no longer in the form are marked deleted.

## day_context.csv (key: date). Mirrors calendar_real.csv and weather_kattankulathur.csv

| Column | Meaning |
|---|---|
| date, day_of_week | the day |
| temp_max_c, temp_min_c, temp_mean_c | temperatures in C, 10 to 50. Mean only when both are given |
| condition, rain_level | weather type from the dropdown and the rain level it means (0 to 3) |
| special_day, special_day_type, special_day_name | holiday, rain_holiday, campus_event or other. Sets special_declared_holiday (and rain_holiday_colleges for a rain holiday) |
| exam_week, exam_type | formative_test or university_exam. Sets formative_test_any or university_exam_any and the exam phase |
| festival, festival_name, festival_scale | major or minor. Sets tn_public_holiday, and major_festival for a major one |

These flow into the features exactly like the calendar columns (`admin/context.py`). Entered phases get `phase_confidence = official`.

## attendance.csv (key: date, meal_slot). Mirrors kitchen_history.csv

| Column | Meaning |
|---|---|
| meal_slot | breakfast, lunch, snacks or dinner |
| attendance | students who ate, 0 to 4000 (enrolled) |
| students_present | students on campus (optional; the largest slot attendance of the day is used when empty) |

## kitchen_log.csv (key: date, meal_slot, dish_id). Mirrors kitchen_history.csv

| Column | Meaning |
|---|---|
| prepared_qty, topup_qty | portions cooked before service and added during service |
| consumed_qty | portions eaten. Empty means "worked out from leftover" |
| leftover_qty | portions left over. Empty means "worked out from eaten" |
| unmet_qty | estimated portions wanted but not served (only when ran_out_early = 1) |
| ran_out_early | 1 when the dish ran out |

At least one of consumed_qty and leftover_qty is required, and eaten plus left over must equal prepared plus top up when both are given.
Demand (the forecast target) is consumed plus unmet.

## ingredient_usage.csv (key: date, ingredient). Mirrors inventory_daily.csv

| Column | Meaning |
|---|---|
| ingredient | name from the 70 ingredient master, or a new one |
| used_kg | kilograms used that day |

## forecast_log.csv (written by Approve and Send back)

One row per dish of the plan that was reviewed: reviewed_at, date, meal_slot, decision (approve or send_back), reviewer, note, dish_id,
p10, p50, p90, recommended, approved_qty (what the person approved, edited quantities included), usual_plan, surplus_risk, overrides
(the what if changes, as JSON), model_trained_to (last day the model had learned from) and data_source (`model_snapshot`).
The Daily log compares approved rows with the logged actuals in "Forecast versus actual".
