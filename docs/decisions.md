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
| 16 | Month and cohort phase one hots are NOT inputs of the demand models (they stay in the feature table and the attendance model uses the phases) | One year of data: no month repeats, so a network memorises it. In validation the unseen combination "senior classes, first years away" made the first CVAE under-predict normal days by 43 percent. Removing them cut validation error by more than half |
| 17 | The CVAE decoder mean starts from log expected attendance (an offset) and learns only the deviation | Demand scales with people. Keeps predictions sensible in unseen situations. Target is still log1p(demand) |
| 18 | KL free bits 0.2 per latent dimension | Without it every latent dimension collapses (KL about 0.0001 nats). With it all 8 stay active (KL about 1 nat). Accuracy is about the same either way (see the collapse table in metrics_summary.md), so the latent space is kept for the generative structure, not because it wins accuracy |
| 19 | Band calibration factor k fitted on validation only: the band is P50 plus k times (P10 or P90 minus P50), in log space | Raw samples cover only 60 to 73 percent. k = 1.35 brings validation to 79 percent. Test coverage is then 85 percent, so k is slightly generous there |
| 20 | Final model is trained on train plus validation for the epochs found in the development run (`--include-test` adds the test period) | Follows the brief. Test stays untouched for honest reporting |
| 21 | Support dishes (bread, butter, chutney ...) use a rate rule, not the CVAE | They are 61 percent of rows, simple and predictable; the rule beats all baselines on val and test |
| 22 | Usual plan uses consumed portions of the last two same weekdays plus 12 percent | What the manager sees. Checked against the data: the manager's real prepared quantity is on average 1.00 times this rule |
| 23 | Weather noise (plus or minus 1.5 C, 10 percent rain level flips) is drawn once per date per epoch during CVAE training | All dishes of a day share one weather forecast |
| 24 | Forecast quantiles are P10, P25, P50, P75, P90; the recommendation is P75 rounded to 5 (under 100) or 10 portions | Per the brief. The decision simulation shows P75 versus P50 and P90 so the trade off is visible |
| 25 | `/api/plan` shows core dishes by default (`scope=core`), all dishes with `scope=all`; headline totals follow the scope | Core dishes are the ones the model forecasts with the CVAE; support dishes are bread, butter, chutney. The dashboard has a "Show all dishes" option |
| 26 | `/api/review` recomputes the forecast on the server and stores it with the decision | The stored snapshot cannot be altered by the browser |
| 27 | NLTK resources are never downloaded implicitly; only the pipeline entry points download | An implicit download made one test run take 48 minutes offline |
| 28 | Chat and admin endpoints are added in their own milestones, not as empty stubs | No dead routes |
| 29 | The Daily log (admin) tab is built in the admin milestone, together with its backend | A form that cannot save would be a dead screen. The view switch is ready for a third tab |
| 30 | The copilot panel is built now and shows a clear "not available on this server" message until the chat endpoint exists | The layout is part of both designs; the message says what happened |
| 31 | Chart days are clickable (and keyboard operable); the week starts tomorrow and the plan day changes inside it | Not in the screenshots, but without it only one day could be inspected |
| 32 | "Change quantities" lets the person edit each dish; Approve stores the edited number as `approved_qty` next to the model's recommendation | Keeps the human decision on record. The copilot still never changes quantities |
| 33 | The dish total row is labelled "Main dishes" (core) or "All dishes" depending on the Show all dishes switch | Honest label: the model forecasts main dishes with the CVAE, support dishes with a rate rule |
| 34 | The Surplus risk panel says the risk is a simple first version | It is the stub for the teammate's detector |
| 35 | Fonts load from Google Fonts with system fallbacks | Per the brief. Offline, the layout still works with system fonts |
| 36 | The copilot answers the first question of a message and says so | Several questions in one message would need several answers; sentence splitting finds them, one is answered |
| 37 | What the question asks decides the code that runs (intent and entities from rules). The language model never chooses | Keeps the system a simple explain pipeline and keeps the behaviour testable |
| 38 | A what if the dashboard cannot try gets a fixed message listing what it can try | Better than guessing a change |
| 39 | Every figure of 10 or more in a model answer must appear in the context JSON, otherwise the template answer is shown | Stops invented numbers. The context therefore carries differences and percentages already worked out |
| 40 | The UI shows where an answer came from (language model or standard wording) | Honest about what wrote the text |
| 41 | `reports/prompt_comparison.md` is only filled with real model answers when a key is present; otherwise it says the model columns were not run | No made up before and after evidence |
| 42 | `tests/test_copilot.py` scans the whole project for the terms the review penalises (the list is in that test) | The review gives negative marks for them, so a slip fails the test instead of the review |
