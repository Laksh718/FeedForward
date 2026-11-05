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
  (probable or estimated). Weather after the history is real: [Open-Meteo](https://open-meteo.com/) (free, no key) for Kattankulathur,
  recorded days up to today and a 16 day forecast, refreshed hourly (`src/feedforward/data/live_weather.py`). Only dates beyond the
  forecast fall back to last year's monthly average, flagged as assumed.
- One year of history: no season repeats, so every score is an estimate. The simulation itself is noisy, which puts a measured ceiling of
  about 95 percent accuracy per dish. See `reports/metrics_summary.md`.

## Folder tree

```
FeedForward/
  Datasets/FEEDFORWARD DATASETS/    read only input data (never edited)
  src/feedforward/
    config.py                       paths, constants, seeds (single source of truth)
    export_code.py                  bundles the data code into artifacts/code_bundle_preprocessing.md
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
    plugins/                        surplus_detector_stub.py (interface), gan_extra_data.py (GAN rows: generate, check, write)
  api/                              FastAPI: main.py, deps.py, schemas.py, services.py, routes/
  app/                              dashboard: index.html, css/, js/ (Home, Service board, Forecast, Plans, Rare events, Copilot, Calendar, Daily log)
  scripts/                          build_static_site.py, deploy_pages.sh (the GitHub Pages online demo)
  data_store/                       calendar_future.csv, schemas/, admin_logs/ (real entries, git ignored)
  artifacts/                        processed data, trained models, nltk data (regenerable, git ignored)
  reports/                          metrics, plots, comparison tables (the review evidence)
  docs/                             pipeline, data dictionary, concept map, objectives map, prompt scenarios, decisions, design/
  tests/                            pytest suite and a browser test (ui_smoke.mjs)
```

## Run it yourself

**Python:** 3.11 or newer is required (`pyproject.toml`). What was actually verified: Python 3.14.0 on Windows with torch 2.12.0 (CPU),
pandas 2.3.3, scikit-learn 1.8.0 and fastapi 0.143.0. The full test suite, the API and the browser test all ran on that set.
A clean Python 3.12 virtual environment installed the packages, but torch could not be imported on the test PC (a DLL error, probably a missing
Visual C++ runtime), so 3.12 is not verified. The README steps below were not re-run on a fresh clone; the model and processed tables are committed,
so the server can start straight after the install steps even before the pipeline is rebuilt.

Windows (PowerShell):

```powershell
py -3.14 -m venv .venv                # or another Python 3.11+ that has CPU torch wheels
.\.venv\Scripts\Activate.ps1
pip install --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt
pip install -e .
Copy-Item .env.example .env        # then edit .env: GEMINI_API_KEY (optional), ADMIN_PIN
```

macOS or Linux:

```bash
python3 -m venv .venv_mac
source .venv_mac/bin/activate
pip install -r requirements.txt
pip install -e .
cp .env.example .env               # then edit .env: GEMINI_API_KEY (optional), ADMIN_PIN
```

NLTK data (needed by the text pipeline and one test; run once, it needs internet):

```bash
python -m nltk.downloader -d artifacts/nltk_data punkt_tab wordnet averaged_perceptron_tagger_eng stopwords
```

Build the data and models once (the table below has the detail), then start the API and open http://127.0.0.1:8000/:

```bash
python -m feedforward.data.preprocess && python -m feedforward.data.cleaning && python -m feedforward.data.calendar_future
python -m feedforward.data.timeseries && python -m feedforward.data.inventory_features
python -m feedforward.models.train && python -m feedforward.models.train --final
uvicorn api.main:app --reload
```

`.env` keys: `GEMINI_API_KEY` and `GEMINI_MODEL` (default `gemini-3.1-flash-lite`; key from [Google AI Studio](https://aistudio.google.com/apikey))
for the copilot's language model, one request per answer. Without a key the copilot uses standard wording. `ADMIN_PIN` is needed for the Daily log. `FEEDFORWARD_LIVE_WEATHER=0` switches the live weather off
(the tests do this). Secrets stay in `.env`; it is never committed.

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
| Learn from real entries | `python -m feedforward.models.train --include-admin`, then `--final --include-admin` | uses the Daily log rows; refuses with fewer than 28 real days unless you add `--force` |
| Prompt comparison (needs a key) | `python -m feedforward.copilot.compare_prompts` | `reports/prompt_comparison.md` |
| Start the API and dashboard | `uvicorn api.main:app --reload` | http://127.0.0.1:8000/ (API docs at `/docs`) |
| Tests | `pytest -q` | 162 tests: 161 pass and 1 is skipped when NLTK WordNet data is missing (see the NLTK data step above) |
| Browser test | `node tests/ui_smoke.mjs` (Node 22, Edge, server on port 8765 with `ADMIN_PIN=1234` and a temp `FEEDFORWARD_ADMIN_LOG_DIR`) | PASS or FAIL per interaction |
| Bundle the data code into one document | `python -m feedforward.export_code` | `artifacts/code_bundle_preprocessing.md` |

The tests need the processed data and the final model: run the preprocessing steps and the two training commands once after a fresh clone.

## The dashboard

Open the server address. It opens on a **Home** landing page: a live preview of the next plan, the pipeline in plain language, why the
forecast is a range, and a shortcut to each view. The glass bar at the top switches the view (on a phone it becomes a dock at the bottom of
the screen; the arrow keys move between the tabs).

Every view reads the same saved plans. A decision, a Daily log save or an automatic run made on any page (or in another tab, or by
the automation) shows on all the others within seconds: the page asks the server every 15 seconds whether anything was saved
(`GET /api/activity/version`) and reloads only when it was.

- **Home**: the landing page plus **Where the kitchen stands**: the next 7 days as a grid of meals coloured by status (click one to open it),
  the rare days coming up on the calendar (click to plan for one) and the latest activity.
- **Service board**: one meal in full. Pick the slot and the day, then the headline, the day's context, the total to cook against the likely
  range and the usual plan, dish tickets with range bars (search and filters), the week chart and **Try a what if**. **Approve**, **Send
  back** or **Withdraw decision**; **Change quantities** edits each dish first. The side shows this meal over the next days and the latest
  activity.
- **Forecast**: the next 7 days of one meal slot: a card per day (total to cook, likely range, against the usual plan, expected attendance,
  exam or holiday, status), the week chart next to the week before, **every dish on every day** in one table, and the detail and surplus
  risk of the day you pick. Move a week back or forward; switch main dishes or all dishes.
- **Plans**: every meal of the next 7 days on one board with its status (waiting, approved, approved automatically, sent back) and whether it
  is logged. Approve, send back or withdraw one plan, a whole day, every waiting plan, or a selection; filter by status.
- **Rare events**: pick a festival, holiday or campus event, exam week or heavy rain, a day and a meal (or click one of the rare days coming
  up). It shows the normal plan, the forecast with the event applied, and a few hundred possible days **generated by the rare event GAN**
  (a histogram of the total, and per dish typical and range), with a verdict per dish (covered, may run short, may be left over), the
  ingredients the change needs, and three quantities to choose from: the forecast, a generated typical day or a generated busy day. Approve
  it for this meal, or for several days and meals at once (an exam week).
- **Copilot**: a conversation about one plan. On the left, the plan it is reading (pick the day and meal) and questions to try; on the
  right, the answers. It explains the numbers and never changes or approves a plan.
- **Calendar**: a month view of the real academic calendar (Tamil Nadu public holidays, festivals, exam and test phases), cross-checked
  against a live public holiday calendar, with a mark per reviewed meal (green approved, red sent back). Click a day to open its plan;
  **Plan for it** next to a coming event opens Rare events for it.
- **Daily log** (PIN): a status strip, **Automation** (below), five sections (day context, attendance, dishes and quantities, ingredients,
  review and save), **Fill the whole day from the approved plans**, removable dish rows, bulk import from CSV, recent entries with edit and
  delete, CSV export and "Forecast versus actual".

**Accounts, documents and donations** (the account button at the top right; Calendar, Daily log, Donations and Documents sit
under **More** in the top bar):

- **Account**: sign in, or create an account. A *kitchen* account (a mess, hostel or central kitchen) needs the invite code, which is
  the `ADMIN_PIN`; it opens the Daily log without the PIN, uploads documents and approves NGOs. An *NGO or help group* account
  (food bank, night shelter, children's home, home for the elderly, community kitchen, relief group) can register any time and asks
  for food once a kitchen has approved it. An NGO account sees only **Food offers** and its account: the planning views are the
  kitchen's. **Try as a demo kitchen** and **Try as a demo NGO** sign in to shared demo accounts with one click, and five example
  NGOs (made up names, marked "demo") are there to send food to. Set `FEEDFORWARD_DEMO=off` for a real kitchen. Passwords are
  stored as salted PBKDF2 hashes; a session lasts 14 days.
- **Documents** (retrieval augmented generation): upload SOPs, food safety rules, donation policies or menus (PDF, Word .docx, text,
  Markdown or CSV). Each file is cut into passages and searched with TF-IDF over stemmed words and kitchen synonyms (no outside
  service, the same question always finds the same passages). **Ask your documents** answers from the best passages (worded by the
  language model when one is set up, which may only use those passages; otherwise the passage itself) and shows them with their
  page. The copilot puts matching passages next to the forecast figures and lists them under its answer; a question about the
  SOP, a rule or a policy is answered from the documents. **Rules found** lists the hand over time for surplus food, hot and cold
  holding temperatures, safety margin and smallest donation, each with the sentence it came from; Donations uses them.
- **Donations**: a kitchen fills an offer from the Daily log leftovers, or from the plan's expected surplus (approved quantity, or
  the usual plan when not approved yet, minus the most likely demand), edits it, and sends it to every approved NGO or to one NGO
  picked from the directory. The collection deadline comes from the documents' hand over rule (2 hours if none). NGOs ask for
  portions with a pickup time; the kitchen accepts, declines or marks the food collected. **Rare events** shows how much food the
  normal plan would leave over on an event day, with **Offer this surplus to NGOs**. Offers, requests and collections show in the
  activity feed of every view.

**Automation** (Daily log, both switches off until an admin turns them on; the server checks every 5 minutes, **Run now** does it at once):

- *Approve plans automatically*: every plan from today to N days ahead (1 to 14) that nobody has reviewed is approved with the recommended
  quantities, marked "Approved automatically". A plan a person sent back is never approved automatically.
- *Fill the Daily log from approved plans*: once a day has passed, a day of the last two weeks with approved plans and no entry is filled
  from them (prepared = approved, eaten = most likely, the rest left over, attendance = expected, ingredients from the recipes). It is
  marked "Filled automatically"; the model does **not** learn from it, and forecast versus actual leaves it out, until a person checks the
  numbers and saves the day. Set `FEEDFORWARD_AUTOMATION=off` to stop the background runs.

The look is one small design system in `app/css/base.css` (main colours: ink #0D2A1E, brand green #12855A, usual plan red #C8432A, page background #E8F3ED) (glass surfaces over a slowly drifting background, a sliding pill under every
segmented control, numbers that roll to their new value, charts that draw in when their data changes); the motion helpers live in
`app/js/fx.js`, the logo in `app/js/logo.js` and the icons in `app/js/icons.js`. Everything respects the system's reduce motion setting.

Click a day in a chart to see that day. "Main dishes" are the dishes the CVAE forecasts; "Show all dishes" adds the support dishes (bread, butter, chutney).

## API

| Endpoint | What it does |
|---|---|
| GET /api/health | status, project today, default plan date, data source chip |
| GET /api/plan?date=&slot=&scope= | per dish range, recommended, usual plan, surplus risk, headline sentences |
| GET /api/week?slot=&start=&dish_id= | 7 forecast days plus the last 7 days with actuals before the start |
| POST /api/whatif | plan with changes next to the unchanged plan |
| POST /api/review, GET /api/review | Approve, Send back or Withdraw with a forecast snapshot; the standing decision |
| GET /api/plans?start=&days= | every meal of the next days: totals, risk, standing decision, logged or not, automation status |
| POST /api/plans/review | the same decision on many plans at once |
| GET /api/reviews?start=&end= | decisions only, for a date range (the calendar marks) |
| GET /api/forecast/days?slot=&start=&days= | one slot over several days, dish by dish |
| GET /api/events, POST /api/events/plan, POST /api/events/approve | rare event types and coming rare days; an event plan with GAN generated demand; approve event plans for several days |
| GET /api/activity, GET /api/activity/version | decisions, log saves and automatic runs, newest first; a token that changes when anything is saved |
| POST /api/chat | one explanation: answer, source (llm, template or rules), intent, figures used |
| GET /api/dishes, /api/ingredients | catalogues |
| GET /api/calendar?month=YYYY-MM | one month of the academic calendar, cross-checked against a live public holiday calendar |
| /api/auth/... | register, login, logout, me, demo (one click demo kitchen or NGO), options |
| /api/accounts, /api/accounts/{id}/status | a kitchen lists accounts and approves or switches off NGOs |
| /api/knowledge, /upload, /{id} (DELETE), /search, /ask | the document library: upload (base64 JSON), search passages, answer from them, rules found |
| /api/donations, /suggest, /{id}/claim, /{id}/claims/{cid}, /{id}/cancel | offers of surplus food, suggestions from the log or the plan, requests, accept, collected |
| /api/admin/... (header `X-Admin-Pin`) | menu, validate, day (save), recent, entry (soft delete), export, import (bulk CSV), fill-recipes, plan-fill, automation (GET, POST, run), forecast-vs-actual, summary |

Errors always say what happened and how to fix it. CORS is closed unless `CORS_ORIGINS` is set.

## Online demo on GitHub Pages

GitHub Pages serves files only, so it cannot run the Python model. `scripts/build_static_site.py` calls the real API in process
(same code, same trained model, same numbers) and saves every answer the dashboard can ask for as JSON under `site/data/`, next to
a copy of `app/`. A marker in the built `index.html` switches the page into static mode (`app/js/static-api.js`), which reads the
snapshot instead of calling `/api`. Served by uvicorn, the page behaves exactly as before.

The published page also knows the deployed server on Render (a `feedforward-api` meta tag, set with `--api-url`; see "Deploy the full
version on Render"). The snapshot answers instantly what it holds; everything else goes to that server, so the online site has the
full feature set while the server is up, and falls back to the snapshot's behaviour when it is not:

| In the online site | From the snapshot | From the server (Render) |
|---|---|---|
| Service board, Forecast | every date from 2025-10-06 to 2027-01-31, every slot, main dishes and all dishes, the week chart per dish | other weeks |
| Calendar | every month, as cross-checked against the live holiday calendar when the snapshot was built | |
| What if | one setting at a time for the 7 days from the project's tomorrow | combined settings, any date |
| Copilot | if the server is down: the suggested questions for those 7 days, in the template wording | every question, answered by the language model |
| Approve, Send back | if the server is down: saved in the visitor's own browser only | saved in the server's review log |
| Daily log | off when there is no server | the full Daily log, behind the PIN |

The server only accepts these calls because its `CORS_ORIGINS` includes `https://laksh718.github.io` (set in `render.yaml`). A free
server sleeps when idle, so the page sends it a wake up call as soon as it opens. Add `?remote=off` to the address to use the
snapshot alone, or build with `--api-url ""` to leave the server out.

Local Daily log entries and reviews never go into the snapshot (the build uses an empty admin folder), and no API key is used.

Publish or refresh it (project folder, venv active, after the pipeline has built `artifacts/`):

```bash
scripts/deploy_pages.sh                # builds site/ (about 10 minutes) and pushes it to the gh-pages branch
scripts/deploy_pages.sh --reuse-data   # only app/ changed: refresh the page files, keep the snapshot (seconds)
python scripts/build_static_site.py && python -m http.server -d site 8080   # or just build and look locally
```

Check a build in a browser with `node tests/static_smoke.mjs` (instructions at the top of the file).

The first time, check **Settings, Pages** on GitHub: source "Deploy from a branch", branch `gh-pages`, folder `/ (root)`.

## Deploy the full version on Render (free)

GitHub Pages only serves the prebuilt snapshot. To put the real server online (free copilot questions, any what if, saving reviews and
the Daily log), deploy the repository as a container. The `Dockerfile` installs CPU only torch and the run time packages in
`requirements-deploy.txt` and runs the server as an ordinary user; the trained model and processed tables it needs (about 6 MB under
`artifacts/`) are in git. `render.yaml` holds every Render setting.

1. Sign in at [render.com](https://render.com) with GitHub (no card needed for the free plan).
2. Open [render.com/deploy?repo=https://github.com/Laksh718/FeedForward](https://render.com/deploy?repo=https://github.com/Laksh718/FeedForward),
   or in the dashboard choose **New** > **Blueprint** and pick this repository. If the repository is private, let Render's GitHub app see it.
3. Render reads `render.yaml` (a free Docker web service, health check on `/api/health`, redeploy on every push to `main`) and asks for:
   - `ADMIN_PIN`: a long random PIN, not 1234 (anyone with the link can reach the Daily log page). Until it is set, the Daily log is off.
   - `CORS_ORIGINS` is filled in from `render.yaml` (`https://laksh718.github.io`), so the GitHub Pages site can call the server.
   - `GEMINI_API_KEY`: optional. Use a separate key for this deployment, because every visitor's copilot question uses it. Without a key
     the copilot answers in its template wording.
4. Apply. The first build takes several minutes (torch); the app is then served at the `*.onrender.com` address Render shows.

Good to know on the free plan:
- The server uses about 430 MB of the 512 MB of memory, so a burst of requests can restart it. If that happens often, move to a paid
  instance or a host with more memory.
- A free service sleeps after about 15 minutes without traffic; the next visit wakes it, which takes up to a minute or two.
- Reviews and Daily log entries are written to the container's disk, which is reset on every redeploy or restart. Export the Daily log
  as CSV if you want to keep entries.
- After retraining the model, commit the new `artifacts/models/final`, `artifacts/processed` and `artifacts/timeseries` so the deployment
  uses it.
- The same container runs on any Docker host (the port comes from `PORT`). Koyeb's free plan is closed to new sign ups since it joined
  Mistral AI, and Hugging Face now needs a PRO plan for Docker Spaces.

To try the container on your own machine: `docker build -t feedforward .` then `docker run -p 8000:8000 --env-file .env feedforward` and
open http://localhost:8000.

## Demo script (about 8 minutes)

1. **Idea (1 min):** "A range, not a number, and a person decides." Open the Service board: read the headline and the data source chip
   ("Simulated history"): say plainly that the history is simulated.
2. **Dish tickets (1 min):** pick a dish. Green bar is the likely range, the tick is the most likely amount, the red line is the usual plan.
3. **Week chart (1 min):** click a day; point at the exam week shading.
4. **What if (1 min):** attendance +15 percent, then Exam week; show the summary line "Not saved until you approve".
5. **Copilot (2 min):** on the Copilot view, "Why is Chappathi above the usual plan?", "What if attendance rises 15%?", then "Approve the plan" (it refuses and says why).
   Show the source line under the answer (language model or standard wording).
6. **Human decision (1 min):** Change quantities, edit one dish, Approve. Switch to Plans and the Forecast: the status follows. Approve the rest
   of a day on Plans; open Rare events, pick Deepavali and approve the generated busy day.
7. **Daily log (1 min):** unlock with the PIN, enter yesterday's attendance and two dishes, "Fill from recipes", Save; show the warning for a typo.
   Then `reports/metrics_summary.md` and `docs/objectives_map.md` for the evidence.

## Concepts and evidence for the review

`docs/concept_map.md` (concept, slide topic, where it is used, why it fits, and what does not apply), `docs/pipeline.md`,
`docs/data_dictionary.md`, `docs/objectives_map.md`, `docs/prompt_scenarios.md`, `docs/decisions.md` and the reports folder.

## Rare event GAN

Objective 2: a conditional WGAN-GP learns what demand looks like on rare days (festival, public holiday, exam week, heavy rain) from the
**train period only**, and produces extra synthetic rows. A validator filters them (not below zero, not above 1.3 times the dish's largest real
demand, within the plausible demand per attendee for the dish category, not a copy of a real row). The rows are labelled (`synthetic = 1`,
`source = gan`), down weighted (default 0.3, real rows weigh 1) and never used for validation, calibration or testing.
**Real data is the only truth: in the ablation (`reports/gan_ablation.md`) the GAN rows did not improve the forecasts, so the deployed model does not use them.**

```bash
python -m feedforward.data.gan_data                                     # training table and scaler (artifacts/gan/)
python -m feedforward.models.train_gan --epochs 600 --seed 42           # train the GAN (about 5 minutes on CPU)
python -m feedforward.plugins.gan_extra_data --generate --out artifacts/gan/extra_rows.csv   # make, check and write rows; writes reports/gan_report.md
python -m feedforward.models.train --extra-data artifacts/gan/extra_rows.csv --extra-weight 0.3   # CVAE with the rows (dev run)
python reports/gan_ablation.py                                          # CVAE with and without GAN rows, 3 seeds (about 50 minutes) -> reports/gan_ablation.md
```

Files: `data/gan_data.py` (table, scaler), `models/gan.py` (generator, critic, losses), `models/train_gan.py`, `plugins/gan_extra_data.py`,
`models/gan_report.py`, `reports/gan_report.md`, `reports/gan/` (histograms), `reports/gan_ablation.md`. Outputs in `artifacts/gan/` are not committed.

## Where each teammate plugs in

- **GAN rare event generator:** built, see [Rare event GAN](#rare-event-gan). `plugins/gan_extra_data.py` makes, checks and writes the rows that `train.py --extra-data` reads.
- **Surplus and anomaly detector:** `ForecastService` uses `models/surplus_detector.InventoryAwareSurplusDetector` by default, combining
  the usual plan versus forecast range (demand risk) with days to expiry, stock cover and kilograms expiring soon per dish and date from
  `artifacts/timeseries/inventory_features.parquet` (inventory risk); the higher of the two wins. Swap it for another implementation of
  `assess(usual_plan, p50, p90, **inventory_kwargs)` (see `plugins/surplus_detector_stub.py` for the interface) via `ForecastService(detector=...)`.
- **Decision logic:** read `forecast_log.csv` (approved plans with `approved_qty`) and `ForecastService.forecast(...)`; the copilot never acts.
- **Database:** implement the `LogStore` methods in `admin/store.py` and change `get_store()`.
