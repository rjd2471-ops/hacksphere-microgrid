import argparse
import os
import time
import numpy as np
import pandas as pd
import requests

import json
try:
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "local_secrets.json")) as _f:
        for _k, _v in json.load(_f).items():
            os.environ.setdefault(_k, str(_v))
except FileNotFoundError:
    pass
TOKEN_URL = "https://accounts.zoho.in/oauth/v2/token"
WEATHER = ["ambient_temp_c", "humidity_pct", "solar_irradiance_wm2"]
FEATURES = ["timestamp"] + WEATHER + ["hour", "dayofweek", "is_evening"]
_token = {"value": None, "expires": 0.0}

def get_access_token():
    if _token["value"] and time.time() < _token["expires"]:
        return _token["value"]
    r = requests.post(TOKEN_URL, data={
        "grant_type": "refresh_token",
        "client_id": os.environ.get("ZOHO_CLIENT_ID", ""),
        "client_secret": os.environ.get("ZOHO_CLIENT_SECRET", ""),
        "refresh_token": os.environ.get("ZOHO_REFRESH_TOKEN", ""),
    }, timeout=30)
    r.raise_for_status()
    _token["value"] = r.json()["access_token"]
    _token["expires"] = time.time() + 3000
    return _token["value"]

def build_features(input_df):
    df = input_df.copy()
    ts = pd.to_datetime(df["timestamp"])
    for c in WEATHER:
        df[c] = pd.to_numeric(df[c], errors="coerce")
        df[c] = df[c].interpolate(limit_direction="both")
    df["ambient_temp_c"] = df["ambient_temp_c"].fillna(18.5)
    df["humidity_pct"] = df["humidity_pct"].fillna(70.7)
    df["solar_irradiance_wm2"] = df["solar_irradiance_wm2"].fillna(0.0)
    df["timestamp"] = ts.dt.strftime("%Y-%m-%d %H:%M:%S")
    df["hour"] = ts.dt.hour
    df["dayofweek"] = ts.dt.dayofweek
    df["is_evening"] = ts.dt.hour.between(18, 22).astype(int)
    return df[FEATURES]

def _headers():
    return {
        "X-QUICKML-ENDPOINT-KEY": os.environ.get("QUICKML_ENDPOINT_KEY", "").strip('"\' '),
        "Authorization": f"Zoho-oauthtoken {get_access_token()}",
        "CATALYST-ORG": os.environ.get("CATALYST_ORG", "").strip('"\' '),
        "Environment": "Development",
        "Content-Type": "application/json",
    }

def _call(records):
    endpoint_url = os.environ.get(
    "QUICKML_ENDPOINT_URL",
    "https://api.catalyst.zoho.in/quickml/v1/project/92038000000013024/endpoints/predict")
    r = requests.post(endpoint_url, headers=_headers(),
                      json={"data": records}, timeout=60)
    r.raise_for_status()
    return [float(x) for x in r.json()["result"]]

def _fallback(df):
    hours = pd.to_datetime(df["timestamp"]).dt.hour
    base = 120.0 + 30.0 * np.sin(2 * np.pi * (hours - 6) / 24)
    cool = np.maximum(0.0, df["ambient_temp_c"] - 24.0) * 8.5
    return (base + cool).values

def predict(input_df: pd.DataFrame):
    feats = build_features(input_df)
    records = feats.to_dict(orient="records")
    try:
        try:
            out = _call(records)
            if len(out) == len(records):
                return np.array(out, dtype=float)
        except Exception:
            pass
        return np.array([_call(rec)[0] for rec in records], dtype=float)
    except Exception as e:
        print(f"WARNING: QuickML call failed ({e}). Using dummy fallback.")
        return np.array(_fallback(feats), dtype=float)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="sample_test_input.csv")
    ap.add_argument("--output", default="predictions.csv")
    args, unknown = ap.parse_known_args()

    input_file = args.input
    if not os.path.exists(input_file):
        if os.path.exists("sample_test_input.csv"):
            print(f"Warning: '{input_file}' not found. Falling back to 'sample_test_input.csv'.")
            input_file = "sample_test_input.csv"
        else:
            print(f"Error: Input file '{input_file}' not found.")
            input_file = None

    if input_file:
        df = pd.read_csv(input_file, dtype={"timestamp": str})
        preds = predict(df)
        pd.DataFrame({"timestamp": df["timestamp"],
                      "target_demand_kw": np.round(preds, 2)}
                     ).to_csv(args.output, index=False)
        print(f"Wrote {len(preds)} predictions to {args.output}")
