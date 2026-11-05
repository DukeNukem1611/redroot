"""Step 3 - Take GBIF gridded occurrences, restrict them to each species' NATIVE range (Kew WCVP + TDWG level-3
botanical countries), and compute IUCN criterion-B style range metrics plus data-quality features.

Outputs:
  data/processed/features.csv     one row per species (model input + dashboard)
  data/processed/points.csv.gz    cleaned native points (for the dashboard map)
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import shapely
from pyproj import Geod, Transformer
from shapely.geometry import MultiPoint, shape

from common import INTERIM, PROCESSED, RAW

GRID_DIR = INTERIM / "grid"
GEOD = Geod(ellps="WGS84")
TO_EA = Transformer.from_crs("EPSG:4326", "EPSG:6933", always_xy=True)  # global equal-area (metres)
INDIAN_SUBCONTINENT_L2 = 40  # TDWG level-2 region incl. India, Nepal, Himalaya, Sri Lanka, Bangladesh, Pakistan


# ---------------------------------------------------------------- native ranges (WCVP)
def load_wcvp(names: pd.Series) -> pd.DataFrame:
    """Return per-species native TDWG L3 codes + life form / climate from Kew WCVP."""
    n = pd.read_csv(RAW / "wcvp" / "wcvp_names.csv", sep="|", low_memory=False,
                    usecols=["plant_name_id", "taxon_rank", "taxon_status", "taxon_name",
                             "accepted_plant_name_id", "lifeform_description", "climate_description"])
    n = n[n["taxon_rank"] == "Species"]
    n = n[n["taxon_name"].isin(set(names))]
    # prefer an Accepted record for the name; otherwise follow the synonym to its accepted id
    n["pri"] = (n["taxon_status"] != "Accepted").astype(int)
    n = n.sort_values("pri").drop_duplicates("taxon_name")
    n["acc_id"] = n["accepted_plant_name_id"].fillna(n["plant_name_id"])
    acc = pd.read_csv(RAW / "wcvp" / "wcvp_names.csv", sep="|", low_memory=False,
                      usecols=["plant_name_id", "lifeform_description", "climate_description"])
    acc = acc.set_index("plant_name_id")
    n["lifeform"] = n["acc_id"].map(acc["lifeform_description"]).fillna(n["lifeform_description"])
    n["climate"] = n["acc_id"].map(acc["climate_description"]).fillna(n["climate_description"])

    d = pd.read_csv(RAW / "wcvp" / "wcvp_distribution.csv", sep="|", low_memory=False)
    d = d[(d["introduced"] == 0) & (d["extinct"] == 0) & d["area_code_l3"].notna()]
    nat = d.groupby("plant_name_id").agg(native_l3=("area_code_l3", lambda s: sorted(set(s))),
                                         native_l2=("region_code_l2", lambda s: sorted(set(s))))
    n = n.join(nat, on="acc_id")
    return n[["taxon_name", "taxon_status", "acc_id", "lifeform", "climate", "native_l3", "native_l2"]]


def load_tdwg():
    gj = json.loads((RAW / "tdwg" / "level3.geojson").read_text(encoding="utf-8"))
    codes = [f["properties"]["LEVEL3_COD"] for f in gj["features"]]
    geoms = [shape(f["geometry"]) for f in gj["features"]]
    return np.array(codes), shapely.STRtree(geoms), geoms


def assign_l3(lon, lat, codes, tree):
    """TDWG L3 code for each point; coastal points within ~0.1 deg snap to nearest region."""
    pts = shapely.points(lon, lat)
    out = np.full(len(pts), None, dtype=object)
    idx_pt, idx_geom = tree.query(pts, predicate="within")
    out[idx_pt] = codes[idx_geom]
    miss = np.where(out == None)[0]  # noqa: E711
    if len(miss):
        ip, ig = tree.query_nearest(pts[miss], max_distance=0.1, all_matches=False)
        out[miss[ip]] = codes[ig]
    return out


# ---------------------------------------------------------------- range metrics
def eoo_km2(lon, lat) -> float:
    pts = np.unique(np.round(np.c_[lon, lat], 4), axis=0)
    if len(pts) < 3:
        return 0.0
    hull = MultiPoint(pts).convex_hull
    if hull.geom_type != "Polygon":
        return 0.0
    x, y = hull.exterior.coords.xy
    area, _ = GEOD.polygon_area_perimeter(x, y)
    return abs(area) / 1e6


def cells(lon, lat, size_m: float) -> int:
    x, y = TO_EA.transform(lon, lat)
    return len(set(zip(np.floor(np.asarray(x) / size_m).astype(np.int64),
                       np.floor(np.asarray(y) / size_m).astype(np.int64))))


# ---------------------------------------------------------------- main
def main():
    sp = pd.read_csv(INTERIM / "species.csv").assign(medicinal=True)
    tr = INTERIM / "training_species.csv"
    if tr.exists():
        sp = pd.concat([sp, pd.read_csv(tr).assign(medicinal=False)], ignore_index=True)
        sp = sp.drop_duplicates("speciesKey")
    iucn = pd.read_csv(INTERIM / "iucn.csv")
    counts = pd.read_csv(INTERIM / "gbif_counts.csv")
    sp = sp.merge(iucn, on="speciesKey", how="left").merge(counts, on="speciesKey", how="left")
    rec = INTERIM / "iucn_reconciled.csv"
    sp["iucn_code_gbif"] = sp["iucn_code"]
    if rec.exists():  # step 2b: IUCN categories recovered via synonyms / WCVP accepted names
        r = pd.read_csv(rec).set_index("speciesKey")
        hit = sp["speciesKey"].isin(r.index[r["iucn_source"].notna()])
        sp.loc[hit, "iucn_code"] = sp.loc[hit, "speciesKey"].map(r["iucn_code_reconciled"])
        sp["iucn_source"] = sp["speciesKey"].map(r["iucn_source"])
        print(f"IUCN status recovered via synonyms for {int(hit.sum())} species")

    wc = load_wcvp(sp["accepted_name"])
    sp = sp.merge(wc, left_on="accepted_name", right_on="taxon_name", how="left").drop(columns="taxon_name")
    codes, tree, _ = load_tdwg()

    rows, pts_out = [], []
    for _, s in sp.iterrows():
        key = int(s["speciesKey"])
        r = {"speciesKey": key}
        try:
            g = pd.read_csv(GRID_DIR / f"{key}.csv")
        except (FileNotFoundError, pd.errors.EmptyDataError):
            g = pd.DataFrame(columns=["lon", "lat", "records", "records_dated", "records_since_2000",
                                      "last_year", "zoom"])
        g = g[~((g["lat"].abs() < 0.5) & (g["lon"].abs() < 0.5))]  # null-island artefacts
        r["n_cells_all"], r["n_records_grid"] = len(g), float(g["records"].sum())
        r["grid_zoom"] = int(g["zoom"].iloc[0]) if len(g) else np.nan
        native = s["native_l3"] if isinstance(s["native_l3"], list) else None
        if len(g) and native:
            g = g.assign(l3=assign_l3(g["lon"].values, g["lat"].values, codes, tree))
            g = g[g["l3"].isin(set(native))]
            r["native_filter"] = True
        else:
            r["native_filter"] = False
        r["n_native"] = float(g["records"].sum())
        r["n_native_cells"] = len(g)
        r["frac_native"] = r["n_native"] / r["n_records_grid"] if r["n_records_grid"] else np.nan
        lon, lat = g["lon"].values.astype(float), g["lat"].values.astype(float)
        if len(g):
            r["eoo_km2"] = eoo_km2(lon, lat)
            # each occupied map pixel (>= ~2.4 km) contains >= 1 occupied 2x2 km cell -> AOO lower bound
            r["aoo_km2"] = len(g) * 4.0
            r["n_cells_10km"] = cells(lon, lat, 10_000)
            r["n_cells_50km"] = cells(lon, lat, 50_000)
            w = g["records"].values.astype(float)
            r["lat_median"], r["lon_median"] = float(np.median(lat)), float(np.median(lon))
            r["lat_range"], r["lon_range"] = float(np.ptp(lat)), float(np.ptp(lon))
            r["abs_lat_median"] = abs(r["lat_median"])
            dated = g["records_dated"].sum()
            r["frac_since_2000"] = float(g["records_since_2000"].sum() / dated) if dated else np.nan
            r["last_year"] = float(g["last_year"].max()) if g["last_year"].notna().any() else np.nan
            r["frac_cells_single_record"] = float((w == 1).mean())
            if s["medicinal"]:
                pts_out.append(pd.DataFrame({"speciesKey": key, "lat": g["lat"].round(3), "lon": g["lon"].round(3),
                                             "records": g["records"], "last_year": g["last_year"]}))
        else:
            r.update(eoo_km2=0.0, aoo_km2=0.0, n_cells_10km=0, n_cells_50km=0)
        rows.append(r)

    feat = sp.merge(pd.DataFrame(rows), on="speciesKey", how="left")
    feat["n_native_l3"] = feat["native_l3"].apply(lambda v: len(v) if isinstance(v, list) else np.nan)
    feat["endemic_indian_subcontinent"] = feat["native_l2"].apply(
        lambda v: float(v == [INDIAN_SUBCONTINENT_L2]) if isinstance(v, list) else np.nan)
    feat["capped"] = feat["grid_zoom"] < 4  # coarse grid -> AOO is a (loose) lower bound
    feat["native_l3"] = feat["native_l3"].apply(lambda v: " ".join(v) if isinstance(v, list) else "")
    feat["native_l2"] = feat["native_l2"].apply(lambda v: " ".join(map(str, v)) if isinstance(v, list) else "")
    feat.to_csv(PROCESSED / "features.csv", index=False)
    pd.concat(pts_out).to_csv(PROCESSED / "points.csv.gz", index=False, compression="gzip")
    print(feat.shape, "native filter applied to", int(feat["native_filter"].sum()), "species")
    print(feat["iucn_code"].value_counts(dropna=False).to_dict())


if __name__ == "__main__":
    main()
