# FeedForward: Predict. Prevent. Provide.

FeedForward forecasts meal demand in a hostel mess as a **range** (a low end, a most likely amount and a high end), not a single number.
The kitchen can then cook the right amount, prevent overproduction and spoilage, and redistribute only genuine surplus.
**A human always makes the final decision.** The copilot only explains the numbers; it never changes a quantity or approves a plan.

This repository holds one team member's part: data preprocessing (NLP and tabular), cleaning, feature engineering, a conditional VAE
demand forecaster, the dashboard and copilot, and the admin Daily log that feeds real data back into the forecasts.

**Online demo:** https://laksh718.github.io/FeedForward/ is a read only snapshot of the dashboard, served by GitHub Pages
(see [Online demo on GitHub Pages](#online-demo-on-github-pages)). For everything, [run it yourself](#run-it-yourself).

**Data caveats (read these before quoting any number)**
- The kitchen history is **simulated** on a **real** menu, a **real** calendar and **real** weather. No real world savings are claimed.
- Recipes, portion sizes and popularity scores are estimates. Shelf lives in the inventory are assumed.
- The weather rows for February 2026 are unverified copies of March (`weather_reliable = 0`). One day (2026-05-23) is a flagged temperature outlier.
  Rainfall in millimetres is always 0 in the source and is not used.
- 79 theory exam days are estimates (`phase_confidence = estimated`). Dates after 2026-10-05 come from `data_store/calendar_future.csv`
  (probable or estimated), and future weather is last year's monthly average, always flagged as assumed.
- One year of history: no season repeats, so every score is an estimate. The simulation itself is noisy, which puts a measured ceiling of
  about 95 percent accuracy per dish. See `reports/metrics_summary.md`.

## Folder tree

```
FeedForward/
  Datasets/FEEDFORWARD DATASETS/    read only input data (never edited)
  src/feedforward/
    config.py                       paths, constants, seeds (single source of truth)
    export_code.py                  bundles the data code into docs/code_bundle_preprocessing.md
    data/
      schemas.py loaders.py profile.py            load and validate every file
      nlp_text.py nlp_entities.py nlp_report.py   text pipeline, rule based NER, normalisation report
      text_features.py                            TF-IDF, similarity, SVD dish embedding
      preprocess.py cleaning.py                   normalise tables, clean the raw kitchen file
      calendar_future.py weather_types.py         future calendar, assumed weather, weather dropdown
      feature_registry.py features.py inventory_features.py
      splits.py timeseries.py                     chronological splits, regimes, model datasets
    models/
      prep.py attendance.py baselines.py          scaling, attendance forecaster, baselines and support rule
      cvae.py bundle.py train.py                  conditional VAE, trained bundle, training (dev, --final, --include-admin)
      evaluate.py metrics.py plots.py summary.py  evaluation, plots, reports/metrics_summary.md
      forecast_service.py week_view.py            forecast(...) entry point, 7 day view
    copilot/                        nlu, context_builder, prompts, llm, templates, explain, compare_prompts
    admin/                          schemas, store (LogStore, CsvLogStore), context, history, validation, compare, review_log
    plugins/                        surplus_detector_stub.py, gan_extra_data.py   (teammates plug in here)
  api/                              FastAPI: main.py, deps.py, schemas.py, services.py, routes/
  app/                              dashboard: index.html, css/, js/ (Home, Service board, Forecast desk, Calendar, Daily log)
  scripts/                          build_static_site.py, deploy_pages.sh (the GitHub Pages online demo)
  data_store/                       calendar_future.csv, schemas/, admin_logs/ (real entries, git ignored)
  artifacts/                        processed data, trained models, nltk data (regenerable, git ignored)
  reports/                          metrics, plots, comparison tables (the review evidence)
  docs/                             pipeline, data dictionary, concept map, objectives map, prompt scenarios, decisions, design/
  tests/                            pytest suite and a browser test (ui_smoke.mjs)
```

## Run it yourself

Windows (PowerShell):

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt
pip install -e .
Copy-Item .env.example .env        # then edit .env: GROQ_API_KEY, GROQ_MODEL, ADMIN_PIN
```

macOS or Linux:

```bash
python3 -m venv .venv_mac
source .venv_mac/bin/activate
pip install -r requirements.txt
pip install -e .
cp .env.example .env               # then edit .env: GROQ_API_KEY, GROQ_MODEL, ADMIN_PIN
```

Then run the pipeline steps below once (they build `artifacts/`) and start the server with `uvicorn api.main:app --reload`.

`.env` keys: `GROQ_API_KEY` (optional: without it the copilot uses standard wording), `GROQ_MODEL` (check the name is still available
in your Groq console), `ADMIN_PIN` (needed for the Daily log). Secrets stay in `.env`; it is never committed.

## How to run each part (from the project folder, venv active)

| Step | Command | Output |
|---|---|---|
| Profile the data | `python -m feedforward.data.profile` | shape, dates, missing values of every file |
| Preprocess and normalise text | `python -m feedforward.data.preprocess` | `artifacts/processed/` |
| Clean the raw kitchen file | `python -m feedforward.data.cleaning` | `kitchen_clean.parquet`, `reports/cleaning_log.json` |
| Future calendar | `python -m feedforward.data.calendar_future` | `data_store/calendar_future.csv` |
| Features and time series datasets | `python -m feedforward.data.timeseries` | `artifacts/timeseries/`, `reports/feature_registry.md` |
| Inventory features | `python -m feedforward.data.inventory_features` | `artifacts/timeseries/inventory_features.parquet` |
| NLP report | `python -m feedforward.data.nlp_report` | `reports/nlp_normalisation_report.md` |
| Train (development) | `python -m feedforward.models.train` | `artifacts/models/dev` |
| Evaluate | `python -m feedforward.models.evaluate` | `reports/metrics.json`, `metrics_summary.md`, PNG plots |
| Train the deployed model | `python -m feedforward.models.train --final` | `artifacts/models/final` (train plus validation) |
| Optional GRU experiment | `python -m feedforward.models.train --encoder gru` | `artifacts/models/dev_gru` |
| Learn from real entries | `python -m feedforward.models.train --include-admin`, then `--final --include-admin` | uses the Daily log rows, warns below 28 real days |
| Prompt comparison (needs a key) | `python -m feedforward.copilot.compare_prompts` | `reports/prompt_comparison.md` |
| Start the API and dashboard | `uvicorn api.main:app --reload` | http://127.0.0.1:8000/ (API docs at `/docs`) |
| Tests | `pytest` | 120 plus tests |
| Browser test | `node tests/ui_smoke.mjs` (Node 22, Edge, server on port 8765 with `ADMIN_PIN=1234` and a temp `FEEDFORWARD_ADMIN_LOG_DIR`) | PASS or FAIL per interaction |
| Bundle the data code into one document | `python -m feedforward.export_code` | `docs/code_bundle_preprocessing.md` |

The tests need the processed data and the final model: run the preprocessing steps and the two training commands once after a fresh clone.

## The dashboard

Open the server address. It opens on a **Home** landing page: a live preview of the next plan, the pipeline in plain language, why the
forecast is a range, and a shortcut to each view. The glass bar at the top switches the view (on a phone it becomes a dock at the bottom of
the screen; the arrow keys move between the tabs).

- **Service board** (default once you enter): pick the meal slot and the day (arrows or the date picker), then the headline ("Cook N portions
  for lunch, M fewer than the usual plan"), the day's context (temperature, rain, exam or test week, holidays), a summary card with the total to
  cook against the likely range and the usual plan, dish tickets with range bars, the week chart, "Try a what if" and the copilot. **Approve this plan** saves the plan; **Change quantities** lets you edit each dish
  first. A search box plus category and diet filters narrow the dish tickets down without changing the underlying forecast.
- **Forecast desk**: past week and next 7 days in one chart, the dish by dish table with low end, most likely, high end, usual plan and cook,
  and the surplus risk panel.
- **Calendar**: a month view of the real academic calendar (Tamil Nadu public holidays, festivals, exam and test phases), cross-checked
  against a live public holiday calendar (`GET /api/calendar`) so flagged days show "confirmed online". Click a day to open the Service board
  for it.
- **Daily log** (PIN): a status strip (real days logged, total rows, last entry, progress toward the 28 real day retraining guideline), five
  sections (day context, attendance, dishes and quantities, ingredients, review and save), **bulk import from CSV** (pick a table, upload or
  paste a CSV shaped like its export, preview it, then import; a bad row is skipped and listed, the rest of the file still goes in), recent
  entries with edit and delete, CSV export and "Forecast versus actual".

The look is one small design system in `app/css/base.css` (glass surfaces over a slowly drifting background, a sliding pill under every
segmented control, numbers that roll to their new value, charts that draw in when their data changes); the motion helpers live in
`app/js/fx.js`, the logo in `app/js/logo.js` and the icons in `app/js/icons.js`. Everything respects the system's reduce motion setting.

Click a day in a chart to see that day. "Main dishes" are the dishes the CVAE forecasts; "Show all dishes" adds the support dishes (bread, butter, chutney).

## API

| Endpoint | What it does |
|---|---|
| GET /api/health | status, project today, default plan date, data source chip |
| GET /api/plan?date=&slot=&scope= | per dish range, recommended, usual plan, surplus risk, headline sentences |
| GET /api/week?slot=&start=&dish_id= | 7 forecast days plus the 7 days before as actuals |
| POST /api/whatif | plan with changes next to the unchanged plan |
| POST /api/review, GET /api/review | Approve or Send back with a forecast snapshot; latest decision |
| POST /api/chat | one explanation: answer, source (llm, template or rules), intent, figures used |
| GET /api/dishes, /api/ingredients | catalogues |
| GET /api/calendar?month=YYYY-MM | one month of the academic calendar, cross-checked against a live public holiday calendar |
| /api/admin/... (header `X-Admin-Pin`) | menu, validate, day (save), recent, entry (soft delete), export, import (bulk CSV), fill-recipes, forecast-vs-actual, summary |

Errors always say what happened and how to fix it. CORS is closed unless `CORS_ORIGINS` is set.

## Online demo on GitHub Pages

GitHub Pages serves files only, so it cannot run the Python model. `scripts/build_static_site.py` calls the real API in process
(same code, same trained model, same numbers) and saves every answer the dashboard can ask for as JSON under `site/data/`, next to
a copy of `app/`. A marker in the built `index.html` switches the page into static mode (`app/js/static-api.js`), which reads the
snapshot instead of calling `/api`. Served by uvicorn, the page behaves exactly as before.

| In the online demo | What it holds |
|---|---|
| Service board, Forecast desk | every date from 2025-10-06 to 2027-01-31, every slot, main dishes and all dishes, the week chart per dish |
| Calendar | every month, as cross-checked against the live holiday calendar when the snapshot was built |
| What if | one setting at a time (attendance, special day or weather) for the 7 days from the project's tomorrow |
| Copilot | the suggested questions for those 7 days, in the template wording (no language model) |
| Approve, Send back | saved in the visitor's own browser only |
| Daily log | off: it saves real entries to the server's files |

Local Daily log entries and reviews never go into the snapshot (the build uses an empty admin folder), and no API key is used.

Publish or refresh it (project folder, venv active, after the pipeline has built `artifacts/`):

```bash
scripts/deploy_pages.sh                # builds site/ (about 10 minutes) and pushes it to the gh-pages branch
scripts/deploy_pages.sh --reuse-data   # only app/ changed: refresh the page files, keep the snapshot (seconds)
python scripts/build_static_site.py && python -m http.server -d site 8080   # or just build and look locally
```

Check a build in a browser with `node tests/static_smoke.mjs` (instructions at the top of the file).

The first time, check **Settings, Pages** on GitHub: source "Deploy from a branch", branch `gh-pages`, folder `/ (root)`.

## Deploy the full version on Koyeb (free)

GitHub Pages only serves the prebuilt snapshot. To put the real server online (free copilot questions, any what if, saving reviews and
the Daily log), deploy the repository as a container. The `Dockerfile` installs CPU only torch and the run time packages in
`requirements-deploy.txt`; the trained model and processed tables it needs (about 6 MB under `artifacts/`) are in git.

1. Sign in at [koyeb.com](https://www.koyeb.com) with GitHub, then **Create service** > **Web service** > **GitHub** and pick this
   repository, branch `main`. Allow Koyeb's GitHub app to see the repository if it asks.
2. Builder: **Dockerfile** (found at the repository root). Instance: the **free** one.
3. Environment variables (mark both as secrets):
   - `ADMIN_PIN`: a long random PIN, not 1234 (anyone with the link can reach the Daily log page).
   - `GROQ_API_KEY`: optional. Use a separate key for this deployment, because every visitor's copilot question uses it. Without
     a key the copilot answers in its template wording.
4. Port `8000`, protocol HTTP. Health check: HTTP on path `/api/health`, with a grace period of about two minutes (loading the model
   takes a while on the free instance).
5. Deploy. The app is served at the `*.koyeb.app` address Koyeb shows; every push to `main` redeploys it.

Good to know on the free instance:
- The server uses about 430 MB of the 512 MB of memory, so a burst of requests can restart it. If that happens often, use a bigger
  instance or another host with more memory (Hugging Face Spaces gives 16 GB for free).
- Reviews and Daily log entries are written to the container's disk, which is reset on every redeploy or restart. Export the
  Daily log as CSV if you want to keep entries.
- A free service is paused when it gets no traffic for a while and takes a moment to wake on the next visit.
- After retraining the model, commit the new `artifacts/models/final`, `artifacts/processed` and `artifacts/timeseries` so the
  deployment uses it.

To try the same container on your own machine: `docker build -t feedforward .` then
`docker run -p 8000:8000 --env-file .env feedforward` and open http://localhost:8000.

## Demo script (about 8 minutes)

1. **Idea (1 min):** "A range, not a number, and a person decides." Open the Service board: read the headline and the data source chip
   ("Simulated history"): say plainly that the history is simulated.
2. **Dish tickets (1 min):** pick a dish. Green bar is the likely range, the tick is the most likely amount, the red line is the usual plan.
3. **Week chart (1 min):** click a day; point at the exam week shading.
4. **What if (1 min):** attendance +15 percent, then Exam week; show the summary line "Not saved until you approve".
5. **Copilot (2 min):** "Why is Chappathi above the usual plan?", "What if attendance rises 15%?", then "Approve the plan" (it refuses and says why).
   Show the source line under the answer (language model or standard wording).
6. **Human decision (1 min):** Change quantities, edit one dish, Approve. Switch to the Forecast desk: status now says Approved.
7. **Daily log (1 min):** unlock with the PIN, enter yesterday's attendance and two dishes, "Fill from recipes", Save; show the warning for a typo.
   Then `reports/metrics_summary.md` and `docs/objectives_map.md` for the evidence.

## Concepts and evidence for the review

`docs/concept_map.md` (concept, slide topic, where it is used, why it fits, and what does not apply), `docs/pipeline.md`,
`docs/data_dictionary.md`, `docs/objectives_map.md`, `docs/prompt_scenarios.md`, `docs/decisions.md` and the reports folder.

## Where each teammate plugs in

- **GAN rare event generator:** write synthetic rows with the columns of `artifacts/timeseries/panel.parquet` plus `expected_attendance`
  and run `python -m feedforward.models.train --extra-data FILE`. `plugins/gan_extra_data.py` validates them; they are down weighted
  (`EXTRA_DATA_WEIGHT`) and never used for validation, calibration or testing.
- **Surplus and anomaly detector:** `ForecastService` uses `models/surplus_detector.InventoryAwareSurplusDetector` by default, combining
  the usual plan versus forecast range (demand risk) with days to expiry, stock cover and kilograms expiring soon per dish and date from
  `artifacts/timeseries/inventory_features.parquet` (inventory risk); the higher of the two wins. Swap it for another implementation of
  `assess(usual_plan, p50, p90, **inventory_kwargs)` (see `plugins/surplus_detector_stub.py` for the interface) via `ForecastService(detector=...)`.
- **Decision logic:** read `forecast_log.csv` (approved plans with `approved_qty`) and `ForecastService.forecast(...)`; the copilot never acts.
- **Database:** implement the `LogStore` methods in `admin/store.py` and change `get_store()`.
