"""Step 1b - Regional training set: IUCN-assessed vascular plants with GBIF records in South Asia
(India, Nepal, Sri Lanka, Bangladesh, Pakistan, Bhutan), medicinal or not. Step 3 keeps only those
native to the Indian subcontinent (WCVP).

Only 40 of the medicinal species are officially threatened, which is too few to train a model on.
Adding the regional flora gives >1,000 threatened examples. The model then scores the medicinal species.

Output: data/interim/training_species.csv
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from common import GBIF, INTERIM, get_json

COUNTRIES = ["IN", "NP", "LK", "BD", "PK", "BT"]
TRACHEOPHYTA = 7707728
N_LC_SAMPLE = 1500


def facet_species(cat: str) -> list[int]:
    keys, off = [], 0
    while True:
        d = get_json(f"{GBIF}/occurrence/search", {
            "country": COUNTRIES, "phylumKey": TRACHEOPHYTA, "iucnRedListCategory": cat, "limit": 0,
            "facet": "speciesKey", "facetLimit": 1000, "facetOffset": off}) or {}
        counts = (d.get("facets") or [{}])[0].get("counts", [])
        keys += [int(c["name"]) for c in counts]
        if len(counts) < 1000:
            return keys
        off += 1000


def name(key: int) -> dict:
    d = get_json(f"{GBIF}/species/{key}") or {}
    return {"speciesKey": key, "accepted_name": d.get("species") or d.get("canonicalName"),
            "family": d.get("family"), "order": d.get("order"), "rank": d.get("rank")}


def main():
    cats = {c: facet_species(c) for c in ["CR", "EN", "VU", "NT", "LC"]}
    for c, k in cats.items():
        print(c, len(k))
    rng = np.random.default_rng(0)
    lc = cats.pop("LC")
    lc = list(rng.choice(lc, size=min(N_LC_SAMPLE, len(lc)), replace=False))  # random, not most-recorded
    keys = sorted(set(sum(cats.values(), [])) | set(int(k) for k in lc))
    med = set(pd.read_csv(INTERIM / "species.csv")["speciesKey"])
    keys = [k for k in keys if k not in med]
    with ThreadPoolExecutor(4) as ex:
        t = pd.DataFrame(list(ex.map(name, keys)))
    t = t[t["rank"] == "SPECIES"].drop(columns="rank")
    t.to_csv(INTERIM / "training_species.csv", index=False)
    print(len(t), "non-medicinal regional training species written")


if __name__ == "__main__":
    main()
