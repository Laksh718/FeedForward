# FeedForward: Predict. Prevent. Provide.

Forecasts meal demand in a hostel mess as a range (P10, P50, P90) so the kitchen can cook the
right amount, prevent overproduction and redistribute only genuine surplus. A human always makes
the final decision.

**Data caveat:** the kitchen history is SIMULATED on a real menu, a real calendar and real weather.
No real world savings are claimed. The February 2026 weather rows are unverified copies of March.

## Folder tree (M0)

```
FeedForward/
  Datasets/FEEDFORWARD DATASETS/   read only input data
  src/feedforward/
    config.py                      paths, constants, seeds
    data/                          schemas.py, loaders.py, profile.py (more in M1 and M2)
    models/ admin/ copilot/ plugins/   filled in later milestones
  api/  app/                       backend and dashboard (M4, M5)
  data_store/                      schemas/ and admin_logs/ (real entries, git ignored)
  artifacts/  reports/  docs/  tests/  scripts/
```

## Setup (PowerShell)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt
pip install -e .
Copy-Item .env.example .env   # then edit .env
```

## Run

```powershell
python -m feedforward.data.profile   # profile every dataset
pytest                               # tests
```
