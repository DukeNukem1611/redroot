"""Step 2 - For every species:
  * IUCN Red List category (GBIF mirror of the IUCN checklist; no API token needed)
  * occurrence counts + country / basis-of-record facets (GBIF occurrence search, limit=0)
  * gridded occurrence points from the GBIF Maps API (vector tiles, EPSG:4326). Each tile pixel is
    one occupied grid cell with its record count and per-year counts. At zoom 4 a pixel is
    ~0.022 deg (~2.4 km), close to the 2x2 km IUCN AOO grid; widespread species use coarser zooms.

Outputs:
  data/interim/iucn.csv, data/interim/gbif_counts.csv
  data/interim/grid/<speciesKey>.csv   (lon, lat, records, records_since_2000, records_dated, last_year, zoom)
"""
from __future__ import annotations

import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import mapbox_vector_tile as mvt
import pandas as pd
import requests

from common import GBIF, INTERIM, get_json

GRID_DIR = INTERIM / "grid"
GRID_DIR.mkdir(exist_ok=True)
MAPS = "https://api.gbif.org/v2/map/occurrence/density"
BASIS = ["PRESERVED_SPECIMEN", "HUMAN_OBSERVATION", "OBSERVATION", "MATERIAL_SAMPLE", "OCCURRENCE",
         "MACHINE_OBSERVATION"]  # excludes LIVING_SPECIMEN (botanic gardens) and FOSSIL_SPECIMEN
MAX_TILES = 16
EXTENT = 512
_s = requests.Session()
_s.headers["User-Agent"] = "EthnoHack2026-medicinal-plant-risk/0.1 (research prototype)"


def iucn(key: int) -> dict:
    d = get_json(f"{GBIF}/species/{key}/iucnRedListCategory") or {}
    return {"speciesKey": key, "iucn_code": d.get("code"), "iucn_category": d.get("category"),
            "iucn_taxon_id": d.get("iucnTaxonID")}


def facets(key: int) -> dict:
    d = get_json(f"{GBIF}/occurrence/search", {
        "taxonKey": key, "hasCoordinate": "true", "hasGeospatialIssue": "false", "occurrenceStatus": "PRESENT",
        "limit": 0, "facet": ["countryCode", "basisOfRecord"], "facetLimit": 300}) or {}
    f = {x["field"]: {c["name"]: c["count"] for c in x["counts"]} for x in d.get("facets", [])}
    basis = f.get("BASIS_OF_RECORD", {})
    n = sum(basis.values()) or 0
    return {"speciesKey": key, "gbif_count": d.get("count", 0), "n_countries_gbif": len(f.get("COUNTRY_CODE", {})),
            "frac_specimen": basis.get("PRESERVED_SPECIMEN", 0) / n if n else None,
            "frac_living_specimen": basis.get("LIVING_SPECIMEN", 0) / n if n else None}


def tile(z, x, y, key):
    params = [("srs", "EPSG:4326"), ("taxonKey", key)] + [("basisOfRecord", b) for b in BASIS]
    delay = 2.0
    for attempt in range(9):
        try:
            r = _s.get(f"{MAPS}/{z}/{x}/{y}.mvt", params=params, timeout=60)
            if r.status_code == 204 or not r.content:
                return []
            r.raise_for_status()
            return mvt.decode(r.content).get("occurrence", {}).get("features", [])
        except (requests.RequestException, ValueError):
            if attempt == 8:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 60)


def grid(key: int) -> None:
    out = GRID_DIR / f"{key}.csv"
    if out.exists():
        return
    cap = get_json(f"{MAPS}/capabilities.json", {"taxonKey": key}) or {}
    rows = []
    if cap.get("total"):
        lo_lng, hi_lng = cap["minLng"], cap["maxLng"]  # may exceed 180 when the range wraps the antimeridian
        lo_lat, hi_lat = max(cap["minLat"], -90), min(cap["maxLat"], 90)
        for z in (4, 3, 2, 1, 0):
            size = 180 / 2 ** z
            cols = range(math.floor((lo_lng + 180) / size), math.floor((min(hi_lng, lo_lng + 360) + 180 - 1e-9) / size) + 1)
            rws = range(max(0, math.floor((90 - hi_lat) / size)), min(2 ** z - 1, math.floor((90 - lo_lat - 1e-9) / size)) + 1)
            if len(cols) * len(rws) <= MAX_TILES or z == 0:
                break
        ncol = 2 ** (z + 1)
        for cx in cols:
            x = cx % ncol
            for y in rws:
                for f in tile(z, x, y, key):
                    px, py = f["geometry"]["coordinates"]
                    if not (0 <= px < EXTENT and 0 <= py < EXTENT):
                        continue  # tile buffer duplicates
                    p = f["properties"]
                    years = {int(k): v for k, v in p.items() if k.isdigit() and int(k) > 0}
                    rows.append({
                        "lon": -180 + (x + (px + 0.5) / EXTENT) * size,
                        "lat": 90 - (y + 1) * size + (py + 0.5) / EXTENT * size,  # decoder returns y-up
                        "records": p.get("total", 0),
                        "records_dated": sum(years.values()),
                        "records_since_2000": sum(v for k, v in years.items() if k >= 2000),
                        "last_year": max(years) if years else None, "zoom": z})
    pd.DataFrame(rows, columns=["lon", "lat", "records", "records_dated", "records_since_2000", "last_year",
                                "zoom"]).to_csv(out, index=False)


def main():
    keys = pd.read_csv(INTERIM / "species.csv")["speciesKey"].astype(int).tolist()
    tr = INTERIM / "training_species.csv"
    if tr.exists():  # regional IUCN-assessed flora (step 1b), fetched after the medicinal species
        keys += [k for k in pd.read_csv(tr)["speciesKey"].astype(int) if k not in set(keys)]
    if len(sys.argv) > 1:
        keys = keys[: int(sys.argv[1])]

    with ThreadPoolExecutor(4) as ex:
        pd.DataFrame(list(ex.map(iucn, keys))).to_csv(INTERIM / "iucn.csv", index=False)
        print("IUCN categories done", flush=True)
        pd.DataFrame(list(ex.map(facets, keys))).to_csv(INTERIM / "gbif_counts.csv", index=False)
        print("facets done", flush=True)

    with ThreadPoolExecutor(5) as ex:
        futs = {ex.submit(grid, k): k for k in keys}
        for i, f in enumerate(as_completed(futs), 1):
            try:
                f.result()
            except Exception as err:  # keep going; a rerun resumes
                print("failed", futs[f], repr(err), flush=True)
            if i % 100 == 0:
                print(f"{i}/{len(keys)} species gridded", flush=True)
    print("done")


if __name__ == "__main__":
    main()
