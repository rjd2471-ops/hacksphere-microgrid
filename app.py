import contextlib
import io
import os

import pandas as pd
from flask import Flask, jsonify, request, send_file

import predict as model  # your working predict.py (same folder)

app = Flask(__name__)

RENEWABLE_KW = 160.0   # above this -> Renewable Storage
OVERLOAD_KW = 200.0    # at or above this -> Critical Overload Alert
CAPACITY_KWH = 1200.0  # assumed battery size (1 hour of demand = demand kWh)
CHARGE_KW = 60.0       # assumed charging per hour on Main Grid


def dispatch(demand_kw, hour):
    """Transition controller: returns (mode, overload_alert)."""
    renewable = demand_kw > RENEWABLE_KW or 18 <= hour <= 22
    return ("Renewable Storage" if renewable else "Main Grid"), demand_kw >= OVERLOAD_KW


def clean(raw):
    need = ["timestamp", "ambient_temp_c", "humidity_pct", "solar_irradiance_wm2"]
    missing = [c for c in need if c not in raw.columns]
    if missing:
        raise ValueError("Missing columns: " + ", ".join(missing))
    df = raw[need].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp").drop_duplicates("timestamp")
    for col, lo, hi in [("ambient_temp_c", -50, 60), ("humidity_pct", 0, 100),
                        ("solar_irradiance_wm2", 0, 1500)]:
        df[col] = pd.to_numeric(df[col], errors="coerce").clip(lo, hi)
        df[col] = df[col].interpolate(limit_direction="both")
    df = df.dropna().head(24)
    if df.empty:
        raise ValueError("No valid rows found in the file.")
    df["timestamp"] = df["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
    return df.reset_index(drop=True)


@app.get("/")
def index():
    return send_file("index.html")


@app.post("/api/forecast")
def forecast():
    try:
        if "file" in request.files:
            raw = pd.read_csv(request.files["file"], dtype={"timestamp": str})
        else:
            raw = pd.read_csv("sample_test_input.csv", dtype={"timestamp": str})
        df = clean(raw)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            preds = model.predict(df)
        used_model = "WARNING" not in buf.getvalue()
    except Exception as exc:
        return jsonify(error=str(exc)), 400

    soc, rows = CAPACITY_KWH, []
    for ts, demand in zip(df["timestamp"], preds):
        demand, hour = float(demand), int(ts[11:13])
        mode, alert = dispatch(demand, hour)
        soc = max(0.0, soc - demand) if mode == "Renewable Storage" else min(CAPACITY_KWH, soc + CHARGE_KW)
        rows.append({"timestamp": ts, "hour": hour, "demand_kw": round(demand, 2),
                     "mode": mode, "overload": alert,
                     "soc_pct": round(100 * soc / CAPACITY_KWH, 1)})
    return jsonify(rows=rows, source="QuickML model" if used_model else "FALLBACK (model call failed)")


if __name__ == "__main__":
    port = int(os.environ.get("X_ZOHO_CATALYST_LISTEN_PORT", 5000))
    app.run(host="0.0.0.0", port=port)
