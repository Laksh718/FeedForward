# FeedForward: Predict. Prevent. Provide.

Forecasts meal demand in a hostel mess as a range (P10, P50, P90) so the kitchen can cook the
right amount, prevent overproduction and redistribute only genuine surplus. A human always makes
the final decision.

**Data caveat:** the kitchen history is SIMULATED on a real menu, a real calendar and real weather.
No real world savings are claimed. The February 2026 weather rows are unverified copies of March.

## Folder tree (after M2)

```
FeedForward/
  Datasets/FEEDFORWARD DATASETS/   read only input data
  src/feedforward/
    config.py                      paths, constants, seeds
    export_code.py                 bundles the data code into docs/code_bundle_preprocessing.md
    data/
      schemas.py loaders.py profile.py          load and validate
      nlp_text.py nlp_entities.py nlp_report.py text pipeline, NER, report
      preprocess.py cleaning.py                 normalise tables, clean the raw kitchen file
      calendar_future.py                        future calendar and assumed weather
      feature_registry.py features.py text_features.py inventory_features.py
      splits.py timeseries.py                   splits, regimes, model datasets
    models/ admin/ copilot/ plugins/   filled in later milestones
  api/  app/                       backend and dashboard (M4, M5)
  data_store/                      calendar_future.csv, schemas/, admin_logs/ (git ignored)
  artifacts/                       processed, timeseries, nltk_data (git ignored)
  reports/  docs/  tests/  scripts/
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
python -m feedforward.data.profile           # profile every dataset
python -m feedforward.data.preprocess        # normalise tables to artifacts/processed
python -m feedforward.data.cleaning          # clean the raw kitchen file, write the log
python -m feedforward.data.calendar_future   # data_store/calendar_future.csv
python -m feedforward.data.timeseries        # panel, windows, registry (run cleaning first)
python -m feedforward.data.inventory_features
python -m feedforward.data.nlp_report        # reports/nlp_normalisation_report.md
python -m feedforward.export_code            # docs/code_bundle_preprocessing.md
pytest
```
