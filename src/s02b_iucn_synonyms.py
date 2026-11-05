"""Step 2b - Taxonomic reconciliation of IUCN status.

GBIF attaches an IUCN category to the name IUCN used. When GBIF treats that name as a synonym, the
accepted species returns NOT_EVALUATED. Example: Saussurea costus is CR, but its GBIF-accepted name
Dolomiaea costus returns NE. When Kew WCVP and GBIF disagree on the accepted name, the status is lost
the same way (Aquilaria agallocha in GBIF = A. malaccensis, CR, in WCVP).

For every medicinal species without a usable category (NE / DD / missing) we check
  (a) species-rank GBIF synonyms, and (b) the WCVP accepted name, for an IUCN category.
A GBIF synonym's status is accepted ONLY for a homotypic synonym, approximated by a shared specific
epithet (e.g. Aucklandia costus = Dolomiaea costus). Heterotypic synonyms that IUCN assessed are
distinct taxa in IUCN's eyes. Withania chevalieri (Cape Verde, CR) is a GBIF and WCVP "synonym" of
ashwagandha, and its CR status must not transfer. Rejected candidates are logged for audit.
The WCVP route goes the other way: our name is the synonym and IUCN assessed the broader accepted species.

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


def synonym_keys(key: int) -> list[tuple[int, str]]:
    keys, off = [], 0
    while True:
        d = get_json(f"{GBIF}/species/{key}/synonyms", {"limit": 100, "offset": off}) or {}
        res = d.get("results", [])
        keys += [(r["key"], r.get("canonicalName") or " ".join(r.get("scientificName", "").split()[:2]))
                 for r in res if r.get("rank") == "SPECIES"]
        if d.get("endOfRecords", True) or not res:
            return keys
        off += 100


def wcvp_accepted_map() -> dict[str, str]:
    """WCVP: every species-rank name -> its accepted species name (accepted names map to themselves)."""
    n = pd.read_csv(RAW / "wcvp" / "wcvp_names.csv", sep="|", low_memory=False,
                    usecols=["plant_name_id", "taxon_rank", "taxon_status", "taxon_name", "accepted_plant_name_id"])
    n = n[n["taxon_rank"] == "Species"]
    acc = n.set_index("plant_name_id")["taxon_name"]
    n = n.assign(acc_name=n["accepted_plant_name_id"].map(acc))
    n.loc[n["taxon_status"] == "Accepted", "acc_name"] = n["taxon_name"]
    n = n[n["acc_name"].notna()].assign(pri=(n["taxon_status"] != "Accepted").astype(int))
    return n.sort_values("pri").drop_duplicates("taxon_name").set_index("taxon_name")["acc_name"].to_dict()


WCVP = {}


def stem(epithet: str) -> str:
    for end in ("ensis", "iana", "ianum", "ianus", "ium", "ius", "ia", "um", "us", "is", "a", "e", "i"):
        if epithet.endswith(end) and len(epithet) - len(end) >= 4:
            return epithet[: -len(end)]
    return epithet


def same_concept(syn_name: str, species_name: str) -> bool:
    """Homotypic proxy: same specific epithet (allowing for gender endings), e.g. Aucklandia costus ->
    Dolomiaea costus, Icica serrata -> Protium serratum. A heterotypic synonym that IUCN assessed was
    treated by IUCN as a distinct taxon (e.g. Withania chevalieri, a Cape Verde endemic), so its
    status must not transfer to the broader species, even when WCVP agrees on the synonymy."""
    parts = syn_name.split()
    return len(parts) >= 2 and stem(parts[1].lower()) == stem(species_name.split()[1].lower())


def reconcile(row) -> dict:
    found, rejected = [], []
    for k, syn in synonym_keys(row.speciesKey):
        code, name = iucn_of(k)
        if code not in ASSESSED:
            continue
        if same_concept(syn, row.accepted_name):
            found.append((code, name, "GBIF synonym, same taxon concept"))
        else:
            rejected.append(f"{name} [{code}]")
    if isinstance(row.wcvp_accepted, str):
        m = get_json(f"{GBIF}/species/match", {"name": row.wcvp_accepted, "kingdom": "Plantae", "strict": "true"}) or {}
        if m.get("speciesKey") and m["speciesKey"] != row.speciesKey:
            code, name = iucn_of(m["speciesKey"])
            if code in ASSESSED:
                found.append((code, name, "WCVP accepted name"))
    rej = "; ".join(rejected) or None
    if not found:
        return {"speciesKey": row.speciesKey, "iucn_code_reconciled": row.iucn_code, "iucn_source": None,
                "rejected_synonym_assessments": rej}
    code, name, how = sorted(found, key=lambda f: ASSESSED.index(f[0]))[0]
    return {"speciesKey": row.speciesKey, "iucn_code_reconciled": code, "iucn_source": f"{name} ({how})",
            "rejected_synonym_assessments": rej}


def main():
    sp = pd.read_csv(INTERIM / "species.csv")[["speciesKey", "accepted_name"]]
    sp = sp.merge(pd.read_csv(INTERIM / "iucn.csv")[["speciesKey", "iucn_code"]], on="speciesKey", how="left")
    todo = sp[~sp["iucn_code"].isin(ASSESSED)].copy()
    WCVP.update(wcvp_accepted_map())
    wa = todo["accepted_name"].map(WCVP)
    todo["wcvp_accepted"] = wa.where(wa != todo["accepted_name"])
    print(f"{len(todo)} unassessed species to reconcile; {todo['wcvp_accepted'].notna().sum()} are WCVP synonyms")
    with ThreadPoolExecutor(4) as ex:
        res = pd.DataFrame(list(ex.map(reconcile, todo.itertuples())))
    changed = res[res["iucn_source"].notna()]
    print(f"{len(changed)} species recovered an IUCN category:", changed["iucn_code_reconciled"].value_counts().to_dict())
    print(f"{res['rejected_synonym_assessments'].notna().sum()} species had synonym assessments rejected "
          "as different taxon concepts")
    res.to_csv(INTERIM / "iucn_reconciled.csv", index=False)


if __name__ == "__main__":
    main()
