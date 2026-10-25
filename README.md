# HackSphere 3.0: Smart Energy Microgrid and Demand Forecasting Engine

Team: Rajveer Dukiya
Live app (Catalyst AppSail): https://appsail-50047137104.development.catalystappsail.in

## What it does
1. A demand model (XGBoost regression) is trained and published in Zoho Catalyst QuickML.
2. A Flask app on Catalyst AppSail accepts a telemetry CSV (timestamp, ambient_temp_c, humidity_pct, solar_irradiance_wm2), cleans it, and builds the features the model was trained on.
3. The app calls the published QuickML endpoint for each hourly row (24-hour window).
4. A transition controller applies the dispatch rules and a dashboard shows demand, power source, alerts and battery charge.

## Architecture
CSV upload -> Flask (cleaning and feature building) -> QuickML endpoint -> rules (`dispatch` in `app.py`) -> dashboard (`index.html`, Chart.js)

`predict.py` is the standalone script used for evaluation. It builds the same features, gets an OAuth access token from a refresh token, calls the endpoint and writes `predictions.csv`.

## Model
- Dataset: `train_telemetry.csv` plus engineered features `hour`, `dayofweek`, `is_evening` (hour 18 to 22).
- Compared in QuickML: Random Forest (RMSE 10.20) and XGBoost (RMSE 8.93, published). Metrics are QuickML's own evaluation on its validation split.
- `timestamp` is dropped before training. The features are recomputed from it in `predict.py` and `app.py`.

## Transition rules
- Renewable Storage Mode: predicted demand above 160 kW, or hour between 18 and 22 inclusive.
- Main Grid Mode: otherwise.
- Critical Overload Alert: demand of 200 kW or more, independent of mode.
- `python test_rules.py` checks the edge cases (160, 200, hours 17, 18, 22, 23).

Battery state of charge is not defined by the problem statement. Assumptions used: 1,200 kWh capacity, starts full, discharges by the hour's demand (kWh) in Renewable Storage mode, recharges 60 kW per hour on Main Grid. Change `CAPACITY_KWH` and `CHARGE_KW` in `app.py`.

## Setup
```
pip install -r requirements.txt
```
Set these environment variables (never commit their values):

| Variable | Meaning |
|---|---|
| `QUICKML_ENDPOINT_URL` | Published QuickML endpoint URL (.../endpoints/predict) |
| `QUICKML_ENDPOINT_KEY` | QuickML endpoint key |
| `CATALYST_ORG` | Catalyst organisation ID |
| `ZOHO_CLIENT_ID` | Zoho API Console Self Client ID |
| `ZOHO_CLIENT_SECRET` | Self Client secret |
| `ZOHO_REFRESH_TOKEN` | Refresh token for scope `QuickML.deployment.READ` |

PowerShell example: `$env:QUICKML_ENDPOINT_URL="..."`

## Run
```
python predict.py --input sample_test_input.csv --output predictions.csv
python test_eval.py
python test_rules.py
python app.py        # dashboard at http://localhost:5000
```

## Deploy on Catalyst AppSail
Python 3.12 stack, start command `python3 -u app.py`, port read from `X_ZOHO_CATALYST_LISTEN_PORT`. Libraries are installed into the deploy folder for Linux (`pip install ... -t . --platform manylinux2014_x86_64 --python-version 3.12 --only-binary=:all:`), then `catalyst deploy`.

## Known limits
- If credentials are missing, `predict.py` prints a warning and falls back to a simple formula, so check for that warning.
- The dashboard handles one 24-hour window per run (the first 24 valid rows by time).
