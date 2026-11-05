"""Step 2b - Taxonomic reconciliation of IUCN status.

GBIF attaches an IUCN category to the name IUCN used. When GBIF treats that name as a synonym, the
accepted species returns NOT_EVALUATED. Example: Saussurea costus is CR, but its GBIF-accepted name
Dolomiaea costus returns NE. When Kew WCVP and GBIF disagree on the accepted name, the status is lost
the same way (Aquilaria agallocha in GBIF = A. malaccensis, CR, in WCVP).

For every medicinal species without a usable category (NE / DD / missing) we check
  (a) every species-rank GBIF synonym, and (b) the WCVP accepted name,
for an IUCN category. The most severe category found is used and its source name is recorded.

Output: data/interim/iucn_reconciled.csv
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from common import GBIF, INTERIM, RAW, get_json

ASSESSED = ["EX", "EW", "CR", "EN", "VU", "NT", "LC"]  # severity order (DD/NE are not assessments)


def iucn_of(key: int):
    d = get_json(f"{GBIF}/species/{key}/iucnRedListCategory") or {}
    return d.get("code"), d.get("scientificName")


def synonym_keys(key: int) -> list[int]:
    keys, off = [], 0
    while True:
        d = get_json(f"{GBIF}/species/{key}/synonyms", {"limit": 100, "offset": off}) or {}
        res = d.get("results", [])
        keys += [r["key"] for r in res if r.get("rank") == "SPECIES"]
        if d.get("endOfRecords", True) or not res:
            return keys
        off += 100


def wcvp_accepted(names: set[str]) -> dict[str, str]:
    n = pd.read_csv(RAW / "wcvp" / "wcvp_names.csv", sep="|", low_memory=False,
                    usecols=["plant_name_id", "taxon_rank", "taxon_status", "taxon_name", "accepted_plant_name_id"])
    sp = n[(n["taxon_rank"] == "Species") & n["taxon_name"].isin(names) & (n["taxon_status"] == "Synonym")]
    acc = n.set_index("plant_name_id")["taxon_name"]
    return {r.taxon_name: acc.get(r.accepted_plant_name_id) for r in sp.itertuples()
            if isinstance(acc.get(r.accepted_plant_name_id), str)}


def reconcile(row) -> dict:
    found = []
    for k in synonym_keys(row.speciesKey):
        code, name = iucn_of(k)
        if code in ASSESSED:
            found.append((code, name, "GBIF synonym"))
    if isinstance(row.wcvp_accepted, str):
        m = get_json(f"{GBIF}/species/match", {"name": row.wcvp_accepted, "kingdom": "Plantae", "strict": "true"}) or {}
        if m.get("speciesKey") and m["speciesKey"] != row.speciesKey:
            code, name = iucn_of(m["speciesKey"])
            if code in ASSESSED:
                found.append((code, name, "WCVP accepted name"))
    if not found:
        return {"speciesKey": row.speciesKey, "iucn_code_reconciled": row.iucn_code, "iucn_source": None}
    code, name, how = sorted(found, key=lambda f: ASSESSED.index(f[0]))[0]
    return {"speciesKey": row.speciesKey, "iucn_code_reconciled": code, "iucn_source": f"{name} ({how})"}


def main():
    sp = pd.read_csv(INTERIM / "species.csv")[["speciesKey", "accepted_name"]]
    sp = sp.merge(pd.read_csv(INTERIM / "iucn.csv")[["speciesKey", "iucn_code"]], on="speciesKey", how="left")
    todo = sp[~sp["iucn_code"].isin(ASSESSED)].copy()
    todo["wcvp_accepted"] = todo["accepted_name"].map(wcvp_accepted(set(todo["accepted_name"])))
    print(f"{len(todo)} unassessed species to reconcile; {todo['wcvp_accepted'].notna().sum()} are WCVP synonyms")
    with ThreadPoolExecutor(4) as ex:
        res = pd.DataFrame(list(ex.map(reconcile, todo.itertuples())))
    changed = res[res["iucn_source"].notna()]
    print(f"{len(changed)} species recovered an IUCN category:", changed["iucn_code_reconciled"].value_counts().to_dict())
    res.to_csv(INTERIM / "iucn_reconciled.csv", index=False)


if __name__ == "__main__":
    main()
