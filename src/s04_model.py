"""Step 4 - Predict extinction-risk status of medicinal plants and build the conservation priority list.

Training set: every IUCN-assessed vascular plant native to the Indian subcontinent (regional flora,
step 1b), plus all assessed medicinal species. Threatened = CR/EN/VU; not threatened = NT/LC.

1. Baseline: rule-based preliminary IUCN criterion B from EOO / AOO thresholds, as in ConR / rCAT.
2. ML: gradient-boosted trees on range, geography, sampling-effort, life-form and climate features.
   Medicinal-use features are NOT model inputs, so risk is estimated independently of use and
   use pressure is combined only in the priority score.
3. Validation: cross-validation grouped by plant family, repeated over 5 seeds. Metrics are reported
   on the whole regional set and on the medicinal subset.
4. A 25-member bootstrap ensemble scores the NE/DD medicinal species and reports its spread as uncertainty.
5. Exploratory test: are heavily used medicinal species more often threatened?
6. Decision value: how many threatened species assessors find if they work down RedRoot's ranking,
   against a range-size ranking and random order (out-of-fold).
7. Calibration: reliability of the scores, plus an isotonic map from score to the observed share of
   threatened species (fitted and checked with family-grouped cross-fitting).
8. Explanations: SHAP values from every ensemble member give each species' main score drivers.

Outputs: data/processed/predictions.csv (medicinal species), oof_predictions.csv (training species),
metrics.json, importance.csv
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import shap
from scipy.stats import fisher_exact, mannwhitneyu
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import (balanced_accuracy_score, brier_score_loss, confusion_matrix, f1_score,
                             roc_auc_score)
from sklearn.model_selection import StratifiedGroupKFold

from common import PROCESSED

THREAT = {"CR", "EN", "VU"}
NOT_THREAT = {"LC", "NT"}
LIFEFORMS = ["tree", "shrub", "climber", "perennial", "annual", "geophyte", "epiphyte", "succulent"]
SEEDS = range(5)

FEATURES = [
    # range size (criterion-B logic), log-scaled
    "log_eoo", "log_aoo", "log_cells_10km", "log_cells_50km", "lat_range", "lon_range",
    # geography
    "abs_lat_median", "lat_median", "lon_median", "log_native_l3", "endemic_indian_subcontinent",
    # sampling effort and recency (to separate "rare" from "rarely recorded")
    "log_gbif_count", "log_n_native", "frac_native", "frac_since_2000", "frac_specimen", "last_year",
    "n_countries_gbif", "frac_cells_single_record",
] + [f"life_{l}" for l in LIFEFORMS] + ["climate_tropical", "climate_temperate", "climate_subalpine"]

LABELS = {
    "log_eoo": "Extent of occurrence (log)", "log_aoo": "Area of occupancy (log)",
    "log_cells_10km": "Occupied 10 km cells (log)", "log_cells_50km": "Occupied 50 km cells (log)",
    "lat_range": "Latitudinal span", "lon_range": "Longitudinal span", "abs_lat_median": "|Latitude|",
    "lat_median": "Latitude", "lon_median": "Longitude", "log_native_l3": "Native botanical countries (log)",
    "endemic_indian_subcontinent": "Endemic to Indian subcontinent", "log_gbif_count": "GBIF records (log)",
    "log_n_native": "Native-range records (log)", "frac_native": "Share of records in native range",
    "frac_since_2000": "Share of records since 2000", "frac_specimen": "Share herbarium specimens",
    "last_year": "Most recent record", "n_countries_gbif": "Countries with records",
    "frac_cells_single_record": "Cells with a single record",
}


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for src, dst in [("eoo_km2", "log_eoo"), ("aoo_km2", "log_aoo"), ("n_cells_10km", "log_cells_10km"),
                     ("n_cells_50km", "log_cells_50km"), ("gbif_count", "log_gbif_count"),
                     ("n_native", "log_n_native"), ("use_records_global", "log_use_records"),
                     ("n_native_l3", "log_native_l3")]:
        df[dst] = np.log10(df[src].fillna(0) + 1)
    lf = df["lifeform"].fillna("").str.lower()
    for l in LIFEFORMS:
        df[f"life_{l}"] = lf.str.contains(l).astype(float)
    cl = df["climate"].fillna("").str.lower()
    df["climate_tropical"] = cl.str.contains("tropic").astype(float)
    df["climate_temperate"] = cl.str.contains("temperate").astype(float)
    df["climate_subalpine"] = cl.str.contains("subalpine|alpine|montane").astype(float)
    df["label"] = np.where(df["iucn_code"].isin(THREAT), 1, np.where(df["iucn_code"].isin(NOT_THREAT), 0, -1))
    df["enough_data"] = df["n_native"].fillna(0) >= 3
    df["native_subcontinent"] = df["native_l2"].fillna("").astype(str).str.split().apply(
        lambda v: 40 in {int(float(x)) for x in v})
    df["medicinal"] = df["medicinal"].astype(bool)
    return df


def criterion_b(eoo, aoo):
    """Preliminary category from range size alone (IUCN criterion B thresholds)."""
    cat = np.select([(eoo < 100) | (aoo < 10), (eoo < 5000) | (aoo < 500), (eoo < 20000) | (aoo < 2000)],
                    ["CR", "EN", "VU"], default="LC/NT")
    return cat, (cat != "LC/NT").astype(int)


def model(seed=0):
    return HistGradientBoostingClassifier(max_iter=400, learning_rate=0.04, max_leaf_nodes=15,
                                          min_samples_leaf=15, l2_regularization=1.0,
                                          class_weight="balanced", random_state=seed)


def metrics(y, p, thr=0.5):
    yhat = (p >= thr).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, yhat, labels=[0, 1]).ravel()
    return {"roc_auc": float(roc_auc_score(y, p)) if len(set(y)) > 1 else np.nan,
            "balanced_accuracy": float(balanced_accuracy_score(y, yhat)),
            "sensitivity": tp / (tp + fn) if tp + fn else np.nan,
            "specificity": tn / (tn + fp) if tn + fp else np.nan,
            "f1_threatened": float(f1_score(y, yhat, zero_division=0)),
            "brier": float(brier_score_loss(y, p))}


def summarise(runs):
    return ({k: float(np.nanmean([r[k] for r in runs])) for k in runs[0]},
            {k: float(np.nanstd([r[k] for r in runs])) for k in runs[0]})


def reliability(p, y, bins=10):
    """Reliability table (equal-width bins) and expected calibration error."""
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges) - 1, 0, bins - 1)
    rows, ece = [], 0.0
    for b in range(bins):
        s = idx == b
        if not s.any():
            continue
        rows.append({"lo": float(edges[b]), "hi": float(edges[b + 1]), "n": int(s.sum()),
                     "mean_p": float(p[s].mean()), "observed": float(y[s].mean())})
        ece += s.sum() / len(p) * abs(p[s].mean() - y[s].mean())
    return rows, float(ece)


# plain-language names and display values for score drivers (SHAP groups)
def _fmt(v, f):
    return "unknown" if pd.isna(v) else f(v)


DRIVERS = {
    "log_eoo": ("Extent of occurrence", lambda r: _fmt(r["eoo_km2"], lambda v: f"{v:,.0f} km²")),
    "log_aoo": ("Area of occupancy", lambda r: _fmt(r["aoo_km2"], lambda v: f"≥ {v:,.0f} km²")),
    "log_cells_10km": ("Occupied 10 km cells", lambda r: _fmt(r["n_cells_10km"], lambda v: f"{v:,.0f}")),
    "log_cells_50km": ("Occupied 50 km cells", lambda r: _fmt(r["n_cells_50km"], lambda v: f"{v:,.0f}")),
    "lat_range": ("Latitudinal span", lambda r: _fmt(r["lat_range"], lambda v: f"{v:.1f}°")),
    "lon_range": ("Longitudinal span", lambda r: _fmt(r["lon_range"], lambda v: f"{v:.1f}°")),
    "abs_lat_median": ("Distance from the equator", lambda r: _fmt(r["abs_lat_median"], lambda v: f"{v:.1f}°")),
    "lat_median": ("Latitude", lambda r: _fmt(r["lat_median"], lambda v: f"{v:.1f}°")),
    "lon_median": ("Longitude", lambda r: _fmt(r["lon_median"], lambda v: f"{v:.1f}°")),
    "log_native_l3": ("Native botanical countries", lambda r: _fmt(r["n_native_l3"], lambda v: f"{v:.0f}")),
    "endemic_indian_subcontinent": ("Endemic to the Indian subcontinent",
                                    lambda r: "yes" if r["endemic_indian_subcontinent"] == 1 else "no"),
    "log_gbif_count": ("GBIF records", lambda r: _fmt(r["gbif_count"], lambda v: f"{v:,.0f}")),
    "log_n_native": ("Records in the native range", lambda r: _fmt(r["n_native"], lambda v: f"{v:,.0f}")),
    "frac_native": ("Share of records in the native range", lambda r: _fmt(r["frac_native"], lambda v: f"{v:.0%}")),
    "frac_since_2000": ("Share of records since 2000", lambda r: _fmt(r["frac_since_2000"], lambda v: f"{v:.0%}")),
    "frac_specimen": ("Share of herbarium specimens", lambda r: _fmt(r["frac_specimen"], lambda v: f"{v:.0%}")),
    "last_year": ("Most recent record", lambda r: _fmt(r["last_year"], lambda v: f"{v:.0f}")),
    "n_countries_gbif": ("Countries with records", lambda r: _fmt(r["n_countries_gbif"], lambda v: f"{v:.0f}")),
    "frac_cells_single_record": ("Cells with a single record",
                                 lambda r: _fmt(r["frac_cells_single_record"], lambda v: f"{v:.0%}")),
    "life": ("Life form", lambda r: r["lifeform"] if isinstance(r["lifeform"], str) else "unknown"),
    "climate": ("Climate zone", lambda r: r["climate"] if isinstance(r["climate"], str) else "unknown"),
}
GROUP = {f: ("life" if f.startswith("life_") else "climate" if f.startswith("climate_") else f) for f in FEATURES}


def score_drivers(sv, rows, top=4):
    """Top SHAP drivers per species from a SHAP matrix (log-odds units), grouped into plain-language factors."""
    groups = list(dict.fromkeys(GROUP.values()))
    G = np.column_stack([sv[:, [i for i, f in enumerate(FEATURES) if GROUP[f] == g]].sum(1) for g in groups])
    out = []
    for i, (_, r) in enumerate(rows.iterrows()):
        order = np.argsort(-np.abs(G[i]))[:top]
        out.append(json.dumps([[DRIVERS[groups[j]][0], DRIVERS[groups[j]][1](r), round(float(G[i, j]), 2)]
                               for j in order], ensure_ascii=False))
    return out


def main():
    df = prepare(pd.read_csv(PROCESSED / "features.csv"))
    train_mask = (df["label"] >= 0) & df["enough_data"] & (df["medicinal"] | df["native_subcontinent"])
    lab = df[train_mask].reset_index(drop=True)
    X, y = lab[FEATURES], lab["label"].values
    groups = lab["family"].fillna("NA").values
    med = lab["medicinal"].values.astype(bool)
    print(f"training species: {len(lab)} (medicinal {med.sum()})  threatened: {y.sum()}  "
          f"families: {len(set(groups))}")

    # ---- baseline: criterion B rule
    _, flag_b = criterion_b(lab["eoo_km2"].values, lab["aoo_km2"].values)

    def base_metrics(mask):
        m = metrics(y[mask], flag_b[mask].astype(float))
        m["roc_auc"] = float(roc_auc_score(y[mask], -lab.loc[mask, "log_aoo"]))  # ranking by small AOO
        m["brier"] = np.nan
        return m
    base_all, base_med = base_metrics(np.ones(len(lab), bool)), base_metrics(med)

    # ---- ML: repeated family-grouped CV
    runs_all, runs_med, oof_mean = [], [], np.zeros(len(lab))
    sv_oof = np.zeros((len(lab), len(FEATURES)))  # out-of-fold SHAP, explains the out-of-fold score
    for seed in SEEDS:
        oof = np.zeros(len(lab))
        for tr, te in StratifiedGroupKFold(5, shuffle=True, random_state=seed).split(X, y, groups):
            fm = model(seed).fit(X.iloc[tr], y[tr])
            oof[te] = fm.predict_proba(X.iloc[te])[:, 1]
            sv_oof[te] += np.asarray(shap.TreeExplainer(fm).shap_values(X.iloc[te])) / len(SEEDS)
        runs_all.append(metrics(y, oof))
        runs_med.append(metrics(y[med], oof[med]))
        oof_mean += oof / len(SEEDS)
    ml_all, ml_all_sd = summarise(runs_all)
    ml_med, ml_med_sd = summarise(runs_med)
    # screening threshold: maximise Youden's J (sens + spec - 1) on the regional out-of-fold predictions
    grid_t = np.linspace(0.05, 0.95, 91)
    j = [metrics(y, oof_mean, t)["sensitivity"] + metrics(y, oof_mean, t)["specificity"] for t in grid_t]
    t_star = float(grid_t[int(np.argmax(j))])
    at_t = {"all": metrics(y, oof_mean, t_star), "medicinal": metrics(y[med], oof_mean[med], t_star)}

    # ---- decision value: threatened species found when assessors work down a ranking (out-of-fold).
    # Range rule = smallest AOO first, ties broken by smallest EOO (the logic of criterion B).
    def yield_block(mask):
        yy = y[mask]
        ml = np.cumsum(yy[np.argsort(-oof_mean[mask], kind="stable")])
        rb = np.cumsum(yy[np.lexsort((lab.loc[mask, "log_eoo"].values, lab.loc[mask, "log_aoo"].values))])
        n, rate, half = len(yy), yy.mean(), int(np.ceil(yy.sum() / 2))
        ks = list(range(10, n + 1, 10)) + ([n] if n % 10 else [])
        return {"n": int(n), "n_threatened": int(yy.sum()), "k": ks,
                "redroot": [int(ml[k - 1]) for k in ks], "range_rule": [int(rb[k - 1]) for k in ks],
                "random": [round(float(k * rate), 1) for k in ks],
                "at": {str(k): {"redroot": int(ml[k - 1]), "range_rule": int(rb[k - 1]),
                                "random": round(float(k * rate), 1)} for k in (50, 100, 200, 400) if k <= n},
                "k_half_redroot": int(np.searchsorted(ml, half) + 1),
                "k_half_range_rule": int(np.searchsorted(rb, half) + 1),
                "k_half_random": int(np.ceil(half / rate))}
    assessment_yield = {"all": yield_block(np.ones(len(lab), bool)), "medicinal": yield_block(med)}

    # ---- calibration: raw scores (class-balanced, so inflated) vs an isotonic map, cross-fitted by family
    rel_raw, ece_raw = reliability(oof_mean, y)
    p_cal_cv = np.zeros(len(lab))
    for tr, te in StratifiedGroupKFold(5, shuffle=True, random_state=0).split(X, y, groups):
        p_cal_cv[te] = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1) \
            .fit(oof_mean[tr], y[tr]).predict(oof_mean[te])
    rel_cal, ece_cal = reliability(p_cal_cv, y)
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(oof_mean, y)
    calibration = {"bins_raw": rel_raw, "ece_raw": ece_raw, "brier_raw": float(brier_score_loss(y, oof_mean)),
                   "bins_calibrated": rel_cal, "ece_calibrated": ece_cal,
                   "brier_calibrated": float(brier_score_loss(y, p_cal_cv)),
                   "share_threatened_at_threshold": float(iso.predict([t_star])[0]),
                   "note": "isotonic map from out-of-fold score to observed share threatened; "
                           "checked by family-grouped cross-fitting"}
    pd.DataFrame({"speciesKey": lab["speciesKey"], "accepted_name": lab["accepted_name"], "family": lab["family"],
                  "medicinal": med, "threatened": y, "p_oof": oof_mean, "p_calibrated_cv": p_cal_cv,
                  "eoo_km2": lab["eoo_km2"], "aoo_km2": lab["aoo_km2"], "criterion_b_flag": flag_b}) \
        .to_csv(PROCESSED / "oof_predictions.csv", index=False)

    # ---- ablation: range-only features (what do sampling/biology features add?)
    range_only = ["log_eoo", "log_aoo", "log_cells_10km", "log_cells_50km", "lat_range", "lon_range"]
    abl = []
    for seed in SEEDS:
        oof = np.zeros(len(lab))
        for tr, te in StratifiedGroupKFold(5, shuffle=True, random_state=seed).split(X, y, groups):
            oof[te] = model(seed).fit(lab[range_only].iloc[tr], y[tr]).predict_proba(lab[range_only].iloc[te])[:, 1]
        abl.append(roc_auc_score(y, oof))

    # ---- final ensemble on all training data (bootstrap bags -> uncertainty)
    rng = np.random.default_rng(42)
    members = []
    for b in range(25):
        idx = rng.choice(len(lab), len(lab), replace=True)
        members.append(model(b).fit(X.iloc[idx], y[idx]))

    out = df[df["medicinal"]].copy()
    P = np.column_stack([m.predict_proba(out[FEATURES])[:, 1] for m in members])
    out["p_threatened"] = P.mean(1)
    out["p_threatened_lo"] = np.percentile(P, 10, axis=1)
    out["p_threatened_hi"] = np.percentile(P, 90, axis=1)
    out.loc[~out["enough_data"], ["p_threatened", "p_threatened_lo", "p_threatened_hi"]] = np.nan
    out["criterion_b_prelim"], _ = criterion_b(out["eoo_km2"].fillna(0).values, out["aoo_km2"].fillna(0).values)
    out.loc[~out["enough_data"], "criterion_b_prelim"] = "insufficient data"
    out.loc[out["capped"].astype(bool) & ~out["criterion_b_prelim"].isin(["LC/NT", "insufficient data"]),
            "criterion_b_prelim"] += " (AOO lower bound)"
    oof_map = dict(zip(lab["speciesKey"], oof_mean))
    out["p_threatened_oof"] = out["speciesKey"].map(oof_map)  # honest, out-of-fold for assessed species
    # observed share of threatened species among assessed species with a similar score
    for src, dst in [("p_threatened", "p_calibrated"), ("p_threatened_oof", "p_calibrated_oof")]:
        ok = out[src].notna()
        out[dst] = np.nan
        out.loc[ok, dst] = iso.predict(out.loc[ok, src].values)
    # main score drivers (SHAP) for scored species: from the ensemble for unassessed species, and from the
    # cross-validation models that never saw the species' family for assessed ones, so each explanation
    # matches the score the website shows
    sc = out["enough_data"].values
    sv = np.mean([np.asarray(shap.TreeExplainer(m).shap_values(out[FEATURES])) for m in members], axis=0)
    row_of = {k: i for i, k in enumerate(lab["speciesKey"])}
    for i, k in enumerate(out["speciesKey"]):
        if k in row_of:
            sv[i] = sv_oof[row_of[k]]
    out["drivers"] = None
    out.loc[sc, "drivers"] = score_drivers(sv[sc], out.loc[sc])

    # ---- priority: no usable IUCN assessment, ranked by risk x medicinal demand
    out["use_pressure_pct"] = out["use_records_global"].rank(pct=True)
    out["priority_score"] = out["p_threatened"] * (0.5 + 0.5 * out["use_pressure_pct"])
    out["assessment_gap"] = out["iucn_code"].isin(["NE", "DD"]) | out["iucn_code"].isna()
    # mostly recorded outside the native range -> widely cultivated / naturalised; wild status uncertain
    out["widely_cultivated"] = (out["frac_native"] < 0.2) & (out["n_records_grid"] >= 100)
    out["native_range_unknown"] = ~out["native_filter"].astype(bool)
    out["screen_threatened"] = out["p_threatened"] >= t_star
    # harvest watchlist: range looks safe, but the species is used more than the median and its biology
    # suits wild harvest (native to the subcontinent, not an annual, regionally rather than globally
    # distributed, mostly wild-recorded). Range-based screening is blind here.
    def harvest_profile(d, p_col):
        return ((d[p_col] < t_star) & (d["use_pressure_pct"] >= 0.5) & d["native_subcontinent"]
                & ~d["lifeform"].fillna("").str.contains("annual") & d["native_filter"].astype(bool)
                & (d["n_native_l3"] <= 15) & (d["frac_native"] >= 0.5) & d["enough_data"])
    out["harvest_watchlist"] = out["assessment_gap"] & harvest_profile(out, "p_threatened")
    # exploratory check on assessed species (out-of-fold): is the profile enriched for threatened species?
    chk = out[out["p_threatened_oof"].notna()].copy()
    chk["y"] = chk["iucn_code"].isin(THREAT).astype(int)
    in_rule = harvest_profile(chk, "p_threatened_oof")
    rest = (chk["p_threatened_oof"] < t_star) & ~in_rule
    tab = [[int((in_rule & (chk["y"] == 1)).sum()), int((in_rule & (chk["y"] == 0)).sum())],
           [int((rest & (chk["y"] == 1)).sum()), int((rest & (chk["y"] == 0)).sum())]]
    fe = fisher_exact(tab)
    watch_check = {"n_in_profile": sum(tab[0]), "threatened_in_profile": tab[0][0],
                   "rate_in_profile": tab[0][0] / max(1, sum(tab[0])), "rate_other_range_safe": tab[1][0] / sum(tab[1]),
                   "odds_ratio": float(fe.statistic), "fisher_p": float(fe.pvalue), "variants_tested": 12,
                   "note": "profile chosen among 12 threshold variants; exploratory, not corrected for multiplicity"}

    # ---- permutation importance (on a held-out family split to avoid optimism)
    tr, te = next(StratifiedGroupKFold(4, shuffle=True, random_state=0).split(X, y, groups))
    m0 = model(0).fit(X.iloc[tr], y[tr])
    imp = permutation_importance(m0, X.iloc[te], y[te], scoring="roc_auc", n_repeats=15, random_state=0)
    pd.DataFrame({"feature": FEATURES, "label": [LABELS.get(f, f.replace("_", " ")) for f in FEATURES],
                  "importance": imp.importances_mean, "sd": imp.importances_std}) \
        .sort_values("importance", ascending=False).to_csv(PROCESSED / "importance.csv", index=False)

    # ---- blind spot: which officially threatened medicinal species does range-based screening miss?
    am = out[out["p_threatened_oof"].notna()].copy()
    am["y"] = am["iucn_code"].isin(THREAT).astype(int)
    thr_m = am[am["y"] == 1]
    missed, caught = thr_m[thr_m["p_threatened_oof"] < t_star], thr_m[thr_m["p_threatened_oof"] >= t_star]
    mw = mannwhitneyu(missed["use_records_global"], caught["use_records_global"], alternative="two-sided")
    safe = am[am["p_threatened_oof"] < t_star]
    auc_safe = roc_auc_score(safe["y"], safe["use_records_global"]) if safe["y"].nunique() == 2 else np.nan
    rng_b = np.random.default_rng(0)
    bs = []
    for _ in range(2000):
        smp = safe.iloc[rng_b.integers(0, len(safe), len(safe))]
        if smp["y"].nunique() == 2:
            bs.append(roc_auc_score(smp["y"], smp["use_records_global"]))
    blind = {"n_threatened_medicinal": int(len(thr_m)), "n_missed": int(len(missed)), "n_caught": int(len(caught)),
             "median_use_missed": float(missed["use_records_global"].median()),
             "median_use_caught": float(caught["use_records_global"].median()),
             "median_use_pct_missed": float(missed["use_pressure_pct"].median()),
             "median_use_pct_caught": float(caught["use_pressure_pct"].median()),
             "mannwhitney_p": float(mw.pvalue),
             "missed_examples": missed.sort_values("use_records_global", ascending=False)["accepted_name"].head(8).tolist(),
             "auc_use_among_range_safe": float(auc_safe),
             "auc_use_among_range_safe_ci": [float(x) for x in np.percentile(bs, [2.5, 97.5])]}
    # does the IUCN assessment gap depend on use intensity?
    heavy = out["use_pressure_pct"] >= 0.75
    gap_ = out["assessment_gap"]
    ft = fisher_exact([[int((heavy & gap_).sum()), int((heavy & ~gap_).sum())],
                       [int((~heavy & gap_).sum()), int((~heavy & ~gap_).sum())]])

    gap = {
        "n_species": int(len(out)),
        "n_assessed": int((~gap_).sum()),
        "n_recovered_via_synonyms": int(out["iucn_source"].notna().sum()) if "iucn_source" in out else 0,
        "n_gap_before_reconciliation": int((~out["iucn_code_gbif"].isin(list(THREAT | NOT_THREAT) + ["EX", "EW"])).sum())
        if "iucn_code_gbif" in out else None,
        "n_threatened_official": int(out["iucn_code"].isin(THREAT).sum()),
        "frac_not_assessed_or_dd": float(gap_.mean()),
        "frac_heavily_used_not_assessed_or_dd": float(out.loc[heavy, "assessment_gap"].mean()),
        "frac_light_used_not_assessed_or_dd": float(out.loc[~heavy, "assessment_gap"].mean()),
        "fisher_heavy_vs_gap_p": float(ft.pvalue), "fisher_heavy_vs_gap_or": float(ft.statistic),
        "n_gap_scored": int((gap_ & out["enough_data"]).sum()),
        "n_gap_insufficient_data": int((gap_ & ~out["enough_data"]).sum()),
        "n_gap_predicted_threatened_p50": int(((out["p_threatened"] >= 0.5) & gap_).sum()),
        "n_gap_predicted_threatened_robust": int(((out["p_threatened_lo"] >= 0.5) & gap_).sum()),
        "n_gap_screen_positive": int((out["screen_threatened"] & gap_ & ~out["widely_cultivated"]).sum()),
        "n_gap_screen_positive_native_sc": int((out["screen_threatened"] & gap_ & ~out["widely_cultivated"]
                                                & out["native_subcontinent"] & out["native_filter"].astype(bool)).sum()),
        "n_gap_screen_positive_robust": int(((out["p_threatened_lo"] >= t_star) & gap_ & ~out["widely_cultivated"]).sum()),
        "n_gap_screen_positive_endemic": int((out["screen_threatened"] & gap_ & ~out["widely_cultivated"]
                                              & (out["endemic_indian_subcontinent"] == 1)).sum()),
        "n_harvest_watchlist": int(out["harvest_watchlist"].sum()),
        "n_widely_cultivated": int(out["widely_cultivated"].sum()),
        "iucn_counts": out["iucn_code"].fillna("none").value_counts().to_dict(),
    }
    res = {
        "n_train": int(len(lab)), "n_train_threatened": int(y.sum()), "n_train_medicinal": int(med.sum()),
        "n_train_medicinal_threatened": int(y[med].sum()), "n_families": int(len(set(groups))),
        "baseline_all": base_all, "baseline_medicinal": base_med,
        "ml_all": ml_all, "ml_all_sd": ml_all_sd, "ml_medicinal": ml_med, "ml_medicinal_sd": ml_med_sd,
        "range_only_auc_mean": float(np.mean(abl)), "range_only_auc_sd": float(np.std(abl)),
        "confusion_ml_all": confusion_matrix(y, (oof_mean >= 0.5).astype(int), labels=[0, 1]).tolist(),
        "confusion_baseline_all": confusion_matrix(y, flag_b, labels=[0, 1]).tolist(),
        "confusion_ml_medicinal": confusion_matrix(y[med], (oof_mean[med] >= 0.5).astype(int),
                                                   labels=[0, 1]).tolist(),
        "screening_threshold": t_star, "at_threshold": at_t, "blind_spot": blind, "watchlist_check": watch_check,
        "gap": gap, "assessment_yield": assessment_yield, "calibration": calibration,
    }
    (PROCESSED / "metrics.json").write_text(json.dumps(res, indent=2, default=float))
    out.to_csv(PROCESSED / "predictions.csv", index=False)
    print(json.dumps({k: res[k] for k in res if not k.startswith("confusion")}, indent=1, default=float))


if __name__ == "__main__":
    main()
