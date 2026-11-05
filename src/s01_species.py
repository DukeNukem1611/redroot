"""Step 1 - Build the South Asian medicinal plant species list from Dr. Duke's ETHNOBOT table
and resolve names against the GBIF Backbone Taxonomy.

Output: data/interim/species.csv  (one row per accepted GBIF species)
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from common import GBIF, INTERIM, RAW, SOUTH_ASIA_PREFIXES, get_json


def load_ethnobot() -> pd.DataFrame:
    e = pd.read_csv(RAW / "duke" / "ETHNOBOT.csv", encoding="latin-1", low_memory=False)
    e["GENUS"] = e["GENUS"].fillna("").str.strip()
    e["SPECIES"] = e["SPECIES"].fillna("").str.strip().str.lower()
    # binomial only; drop "sp.", hybrids and empty epithets
    ok = e["GENUS"].str.match(r"^[A-Z][a-z]+$") & e["SPECIES"].str.match(r"^[a-z][a-z\-]+$")
    e = e[ok & ~e["SPECIES"].isin(["sp", "spp"])].copy()
    e["binomial"] = e["GENUS"] + " " + e["SPECIES"]
    e["COUNTRY"] = e["COUNTRY"].fillna("").str.strip()
    e["region"] = e["COUNTRY"].str.extract(r"^([A-Za-z .]+)")[0].fillna("").str.strip()
    e["south_asia"] = e["COUNTRY"].str.startswith(SOUTH_ASIA_PREFIXES)
    e["ACTIVITY"] = e["ACTIVITY"].fillna("").str.strip()
    return e


def match(name: str) -> dict:
    d = get_json(f"{GBIF}/species/match", {"name": name, "kingdom": "Plantae", "strict": "true"}) or {}
    return {
        "binomial": name,
        "gbif_match_type": d.get("matchType"),
        "gbif_confidence": d.get("confidence"),
        "gbif_rank": d.get("rank"),
        "gbif_status": d.get("status"),
        "gbif_kingdom": d.get("kingdom"),
        "speciesKey": d.get("speciesKey"),
        "accepted_name": d.get("species"),
        "family": d.get("family"),
        "order": d.get("order"),
    }


def main():
    e = load_ethnobot()
    sa = e[e["south_asia"]]
    sa_names = sorted(sa["binomial"].unique())
    print(f"{len(sa_names)} binomials with South Asian ethnobotanical records")

    with ThreadPoolExecutor(8) as ex:
        m = pd.DataFrame(list(ex.map(match, sa_names)))
    good = (
        m["gbif_match_type"].isin(["EXACT", "FUZZY"])
        & (m["gbif_confidence"] >= 90)
        & (m["gbif_kingdom"] == "Plantae")
        & m["speciesKey"].notna()
    )
    print(m["gbif_match_type"].value_counts(dropna=False).to_dict())
    m.to_csv(INTERIM / "name_matching.csv", index=False)
    m = m[good].copy()
    m["speciesKey"] = m["speciesKey"].astype(int)

    # Use-pressure features, computed over ALL Duke records (global) for every synonym that maps to the species
    name2key = dict(zip(m["binomial"], m["speciesKey"]))
    # also map global records whose binomial was not in the SA list but share a key (rare) - skip; use SA synonyms
    e = e[e["binomial"].isin(name2key)].copy()
    e["speciesKey"] = e["binomial"].map(name2key)

    g = e.groupby("speciesKey")
    feats = pd.DataFrame({
        "use_records_global": g.size(),
        "use_activities_global": g["ACTIVITY"].nunique(),
        "use_regions_global": g["region"].nunique(),
        "use_records_south_asia": g["south_asia"].sum(),
        "use_activities_south_asia": e[e["south_asia"]].groupby("speciesKey")["ACTIVITY"].nunique(),
        "use_references": g["REFERENCE"].nunique(),
        "duke_names": g["binomial"].agg(lambda s: "; ".join(sorted(set(s)))),
        "top_uses": e[e["south_asia"]].groupby("speciesKey")["ACTIVITY"].agg(
            lambda s: "; ".join(s.value_counts().head(6).index)),
        "sa_communities": e[e["south_asia"]].groupby("speciesKey")["COUNTRY"].agg(
            lambda s: "; ".join(sorted(set(s)))),
    }).fillna({"use_activities_south_asia": 0})

    sp = (m.sort_values("gbif_confidence", ascending=False)
            .drop_duplicates("speciesKey")[["speciesKey", "accepted_name", "family", "order"]]
            .set_index("speciesKey").join(feats).reset_index())
    sp = sp[sp["accepted_name"].notna()]
    sp.to_csv(INTERIM / "species.csv", index=False)
    print(f"{len(sp)} accepted species written to {INTERIM / 'species.csv'}")


if __name__ == "__main__":
    main()
