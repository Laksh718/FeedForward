# Objectives map

How this part of FeedForward answers the five project objectives, and which file or plot proves each one.
Every number comes from SIMULATED kitchen history on a real menu, calendar and weather, so none of this is a claim about
real world savings.

| # | Objective | What was built | Proof |
|---|---|---|---|
| 1 | Forecast demand as a range | A conditional VAE samples 500 plausible outcomes per dish and reports P10, P50 and P90. A calibration step widens the band to reach about 80 percent coverage. Held out coverage: 79 percent on validation, 85 percent on test | `reports/metrics_summary.md`, `reports/fan_chart.png`, `reports/calibration.png`, `reports/error_by_regime.png`, `src/feedforward/models/cvae.py` |
| 2 | Generate realistic rare event scenarios | Sampling from the latent space and the what if controls (attendance, exam week, festival, holiday, weather). The GAN generator is a teammate's job: `--extra-data` adds its synthetic rows to training | `POST /api/whatif`, `src/feedforward/models/forecast_service.py` (overrides), `plugins/gan_extra_data.py`, `docs/prompt_scenarios.md` scenarios 2 and 3 |
| 3 | Detect likely surplus before it happens | The usual plan (manager rule) is compared with the forecast range; a marked first version flags high, medium or low surplus risk per dish. The real detector plugs in through one interface | `plugins/surplus_detector_stub.py`, the risk pills in both views, the Surplus risk panel of the Forecast desk |
| 4 | Recommend prevention first | The recommended quantity (P75, rounded) is shown next to the usual plan, and a simulation on the test period compares cooking choices: P75 leaves 7.2 percent of cooked food over against 11.1 percent for the usual plan, at 1.6 percent unserved demand against 1.5 percent (top ups ignored). P90 matches the manager's shortage level with slightly more leftover, so the model gives a controllable trade off, not a free gain | "Cooking decision simulation" in `reports/metrics_summary.md`, the Cook column of the Forecast desk |
| 5 | Keep the final decision with a human reviewer | Approve and Send back are stored with a snapshot of the forecast. Change quantities lets the person edit each dish and the edit is stored as `approved_qty`. The copilot only explains: it refuses to approve or change anything, and a test checks this. Forecast versus actual shows later how the approved plan compared with what happened | `POST /api/review`, `data_store/schemas/admin_logs.md` (forecast_log), `tests/test_copilot.py` (out of scope actions), the Forecast versus actual table in the Daily log |

## Continuous improvement (stage 9 of the architecture)

The Daily log saves real attendance, dishes and ingredients. They enter the history immediately (lags, usual plan, forecasts) and
`python -m feedforward.models.train --include-admin` retrains with the real rows, keeping their `data_source` and giving them a higher
weight. It warns when fewer than 28 real days exist.
