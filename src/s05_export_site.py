"""Step 5 - Export compact JSON for the static website in docs/ (served by GitHub Pages).

Outputs (docs/data/):
  species.json      one record per medicinal species (short keys, see KEYS)
  metrics.json      validation + headline numbers (copied)
  importance.json   permutation importances
  hotspots.json     0.5-degree cells where unassessed, screened-threatened species occur
  points/<key>.json native-range grid cells per species, [lat, lon, records, last_year]
                    (display only; capped at 1,500 cells by random sample)
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from common import INTERIM, PROCESSED, ROOT

SITE = ROOT / "docs" / "data"
MAX_CELLS = 1500

KEYS = {  # column -> short key in species.json
    "speciesKey": "k", "accepted_name": "n", "family": "f", "lifeform": "lf", "climate": "cl",
    "iucn_code": "iu", "iucn_source": "src", "p_threatened": "p", "p_threatened_lo": "plo",
    "p_threatened_hi": "phi", "p_threatened_oof": "poof", "criterion_b_prelim": "cb", "eoo_km2": "eoo",
    "aoo_km2": "aoo", "n_native": "nn", "frac_native": "fn", "gbif_count": "gc", "use_records_global": "u",
    "use_activities_south_asia": "ua", "use_pressure_pct": "up", "top_uses": "tu", "sa_communities": "sc",
    "assessment_gap": "gap", "widely_cultivated": "cult", "native_range_unknown": "unk",
    "screen_threatened": "scr", "harvest_watchlist": "wl", "native_subcontinent": "nsc",
    "endemic_indian_subcontinent": "end", "enough_data": "ok", "native_l3": "l3",
}
BOOLS = ["assessment_gap", "widely_cultivated", "native_range_unknown", "screen_threatened",
         "harvest_watchlist", "native_subcontinent", "enough_data"]


def clean(v):
    if isinstance(v, (float, np.floating)):
        return None if np.isnan(v) else round(float(v), 4)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    return v


def main():
    SITE.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(PROCESSED / "predictions.csv")
    df["iucn_code"] = df["iucn_code"].fillna("NE")
    for c in BOOLS:
        df[c] = df[c].astype(bool)
    df["endemic_indian_subcontinent"] = (df["endemic_indian_subcontinent"] == 1)
    if "iucn_source" not in df:
        df["iucn_source"] = None
    recs = [{KEYS[c]: clean(r[c]) for c in KEYS} for _, r in df[list(KEYS)].iterrows()]
    (SITE / "species.json").write_text(json.dumps(recs, separators=(",", ":")), encoding="utf-8")

    m = json.loads((PROCESSED / "metrics.json").read_text())
    rec = INTERIM / "iucn_reconciled.csv"
    if rec.exists():
        m["n_rejected_synonyms"] = int(pd.read_csv(rec)["rejected_synonym_assessments"].notna().sum())
    def no_nan(o):  # browsers reject NaN in JSON
        if isinstance(o, dict):
            return {k: no_nan(v) for k, v in o.items()}
        if isinstance(o, list):
            return [no_nan(v) for v in o]
        return None if isinstance(o, float) and np.isnan(o) else o
    (SITE / "metrics.json").write_text(json.dumps(no_nan(m), indent=1, allow_nan=False))
    imp = pd.read_csv(PROCESSED / "importance.csv").head(12)
    (SITE / "importance.json").write_text(imp[["label", "importance", "sd"]].round(5).to_json(orient="records"))

    pts = pd.read_csv(PROCESSED / "points.csv.gz")
    out = SITE / "points"
    out.mkdir(exist_ok=True)
    for key, g in pts.groupby("speciesKey"):
        if len(g) > MAX_CELLS:
            g = g.sample(MAX_CELLS, random_state=0)
        arr = [[round(a, 3), round(b, 3), int(c), int(d) if pd.notna(d) else None]
               for a, b, c, d in g[["lat", "lon", "records", "last_year"]].itertuples(index=False)]
        (out / f"{int(key)}.json").write_text(json.dumps(arr, separators=(",", ":")))

    # hotspots of unassessed, screened-threatened, non-cultivated species (0.5 degree cells)
    sel = df[df["assessment_gap"] & df["screen_threatened"] & ~df["widely_cultivated"]]
    hp = pts[pts["speciesKey"].isin(sel["speciesKey"])].copy()
    hp["cy"] = (np.floor(hp["lat"] / 0.5) * 0.5 + 0.25).round(2)
    hp["cx"] = (np.floor(hp["lon"] / 0.5) * 0.5 + 0.25).round(2)
    names = dict(zip(sel["speciesKey"], sel["accepted_name"]))
    hs = hp.groupby(["cy", "cx"])["speciesKey"].agg(lambda s: sorted({names[k] for k in s})).reset_index()
    hs = [[r.cy, r.cx, r.speciesKey] for r in hs.itertuples()]
    (SITE / "hotspots.json").write_text(json.dumps(hs, separators=(",", ":")))

    size = sum(f.stat().st_size for f in SITE.rglob("*") if f.is_file()) / 1e6
    print(f"{len(recs)} species, {len(hs)} hotspot cells, site data {size:.1f} MB")


if __name__ == "__main__":
    main()
