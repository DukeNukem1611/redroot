"""RedRoot - extinction-risk radar for South Asia's medicinal plants (EthnoHack 2026, Track 3).

Run:  streamlit run app.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).parent
P = ROOT / "data" / "processed"
ASSETS = ROOT / "assets"
st.set_page_config(page_title="RedRoot", page_icon=str(ASSETS / "icon_dark.png"), layout="wide")

CAT_ORDER = ["CR", "EN", "VU", "NT", "LC", "DD", "NE"]
CAT_COLOR = {"CR": "#b2182b", "EN": "#e66101", "VU": "#fdb863", "NT": "#b8e186", "LC": "#4dac26",
             "DD": "#9e9e9e", "NE": "#cfcfcf"}
CAT_NAME = {"CR": "Critically Endangered", "EN": "Endangered", "VU": "Vulnerable", "NT": "Near Threatened",
            "LC": "Least Concern", "DD": "Data Deficient", "NE": "Not Evaluated"}
ACCENT = "#7b6d8d"


@st.cache_data
def load():
    df = pd.read_csv(P / "predictions.csv")
    df["iucn_code"] = df["iucn_code"].fillna("NE")
    for c in ["assessment_gap", "enough_data", "widely_cultivated", "screen_threatened", "harvest_watchlist",
              "capped", "native_range_unknown"]:
        df[c] = df[c].astype(bool)
    pts = pd.read_csv(P / "points.csv.gz")
    m = json.loads((P / "metrics.json").read_text())
    imp = pd.read_csv(P / "importance.csv")
    return df, pts, m, imp


df, pts, M, IMP = load()
gap, blind, T = M["gap"], M["blind_spot"], M["screening_threshold"]

head_logo, head_text = st.columns([1, 2.6], vertical_alignment="center")
head_logo.image(str(ASSETS / "logo_lockup.png"), width="stretch")
head_text.markdown("### Which medicinal plants of South Asia are we losing, and which have never even been "
                   "assessed?")
st.caption("Research prototype · EthnoHack 2026 · Track 3 Biodiversity & Sustainability. "
           "Model outputs are **preliminary, screening-level estimates** for prioritising expert IUCN assessment. "
           "They are not official Red List categories and not medical advice.")

tab_over, tab_prio, tab_watch, tab_sp, tab_val, tab_meth = st.tabs(
    ["Overview", "Priority list", "Harvest watchlist", "Species explorer", "Model validation",
     "Methods & limitations"])

TABLE_COLS = {"accepted_name": "Species", "family": "Family", "iucn_code": "IUCN", "p_threatened": "P(threatened)",
              "p_threatened_lo": "P10", "p_threatened_hi": "P90", "criterion_b_prelim": "Criterion B (prelim.)",
              "eoo_km2": "EOO km²", "aoo_km2": "AOO km² (≥)", "n_native": "Native records",
              "use_records_global": "Use records", "use_activities_south_asia": "Distinct uses (S. Asia)",
              "top_uses": "Most-recorded uses (literature)"}
TABLE_CFG = {"P(threatened)": st.column_config.ProgressColumn(min_value=0, max_value=1, format="%.2f"),
             "P10": st.column_config.NumberColumn(format="%.2f"), "P90": st.column_config.NumberColumn(format="%.2f"),
             "EOO km²": st.column_config.NumberColumn(format="%,.0f"),
             "AOO km² (≥)": st.column_config.NumberColumn(format="%,.0f"),
             "Native records": st.column_config.NumberColumn(format="%,.0f")}


def table(frame: pd.DataFrame, extra: dict | None = None) -> pd.DataFrame:
    cols = {**(extra or {}), **TABLE_COLS}
    return frame[list(cols)].rename(columns=cols)


# ------------------------------------------------------------------ overview
with tab_over:
    c = st.columns(4)
    c[0].metric("Medicinal species analysed", f"{gap['n_species']:,}",
                help="Plant species with ethnobotanical records from South Asia in Dr. Duke's database")
    c[1].metric("No usable IUCN assessment", f"{gap['frac_not_assessed_or_dd']:.0%}",
                help=f"{gap['n_species'] - gap['n_assessed']:,} species are Not Evaluated or Data Deficient. "
                     f"Among the most-used 25% the share is {gap['frac_heavily_used_not_assessed_or_dd']:.0%}.")
    c[2].metric("Unassessed, screened likely threatened", f"{gap['n_gap_screen_positive']}",
                help=f"Ensemble mean P(threatened) of at least {T:.2f}, the screening threshold chosen on "
                     f"validation data. {gap['n_gap_screen_positive_robust']} stay above it at the ensemble's "
                     "10th percentile. Widely cultivated species are excluded.")
    c[3].metric("Harvest watchlist", f"{gap['n_harvest_watchlist']}",
                help="Unassessed species whose range looks safe but whose use and biology match "
                     "harvest-threatened plants: the blind spot of range-based screening (see Harvest watchlist).")

    st.info(f"**Key finding: a blind spot.** Range-based screening, the standard rapid method, catches threatened "
            f"medicinal plants with small ranges but misses widespread, heavily harvested ones. Of the "
            f"{blind['n_threatened_medicinal']} officially threatened medicinal species, the {blind['n_missed']} "
            f"it misses have a median of {blind['median_use_missed']:.0f} recorded uses, against "
            f"{blind['median_use_caught']:.0f} for the {blind['n_caught']} it catches (Mann-Whitney "
            f"p = {blind['mannwhitney_p']:.3f}). Examples: *{', '.join(blind['missed_examples'][:5])}*.")

    left, right = st.columns([1, 1])
    with left:
        cnt = df["iucn_code"].value_counts().reindex(CAT_ORDER).fillna(0).reset_index()
        cnt.columns = ["code", "species"]
        cnt["category"] = cnt["code"].map(CAT_NAME)
        fig = px.bar(cnt, x="species", y="category", orientation="h", color="code", text="species",
                     color_discrete_map=CAT_COLOR, title="Official IUCN status of the species analysed")
        fig.update_layout(showlegend=False, yaxis_title=None, xaxis_title=None, height=380,
                          margin=dict(l=0, r=0, t=40, b=0))
        st.plotly_chart(fig, width="stretch")
    with right:
        d = df[df["enough_data"]].copy()
        d["Status"] = np.where(~d["assessment_gap"], "Assessed by IUCN",
                               np.where(d["screen_threatened"] & ~d["widely_cultivated"],
                                        "Unassessed: screened threatened", "Unassessed: screened not threatened"))
        fig = px.scatter(d, x="eoo_km2", y="use_records_global", color="Status", log_x=True, log_y=True,
                         hover_name="accepted_name", opacity=0.75, height=380,
                         color_discrete_map={"Assessed by IUCN": "#bdbdbd",
                                             "Unassessed: screened threatened": "#d95f02",
                                             "Unassessed: screened not threatened": "#7570b3"},
                         labels={"eoo_km2": "Extent of occurrence, km² (log)",
                                 "use_records_global": "Recorded medicinal uses (log)"},
                         title="Range size vs medicinal demand")
        fig.update_layout(margin=dict(l=0, r=0, t=40, b=0), legend=dict(orientation="h", y=-0.28, title=None))
        st.plotly_chart(fig, width="stretch")

    st.subheader("Where the unassessed, likely-threatened species grow")
    top = df[df["assessment_gap"] & df["screen_threatened"] & ~df["widely_cultivated"]]["speciesKey"]
    pp = pts[pts["speciesKey"].isin(top)].merge(df[["speciesKey", "accepted_name"]], on="speciesKey")
    if len(pp):
        fig = px.density_map(pp, lat="lat", lon="lon", radius=8, zoom=3.2, center=dict(lat=24, lon=82),
                             map_style="carto-positron", height=480, hover_name="accepted_name")
        fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), coloraxis_showscale=False)
        st.plotly_chart(fig, width="stretch")

# ------------------------------------------------------------------ priority list
with tab_prio:
    st.markdown("Species **without** a usable IUCN assessment (Not Evaluated or Data Deficient) that the model "
                f"screens as likely threatened (P(threatened) ≥ {T:.2f} by default). These are candidates for "
                "**expert Red List assessment and field surveys**, not conclusions.")
    f1, f2, f3, f4 = st.columns(4)
    region = f1.radio("Native range", ["Includes Indian subcontinent", "Endemic to Indian subcontinent", "Any"],
                      help="From Kew's World Checklist of Vascular Plants. 'Any' includes plants that are used in "
                           "South Asia but grow elsewhere, e.g. Iranian Ferula species traded for Unani medicine.")
    hide_cult = f1.checkbox("Hide widely cultivated species", value=True,
                            help="Species with under 20% of GBIF records inside their native range, such as "
                                 "black pepper and saffron. Their wild status cannot be judged from occurrence data.")
    hide_unknown = f1.checkbox("Hide species with unknown native range", value=True)
    min_p = f2.slider("Min. P(threatened)", 0.0, 1.0, float(round(T, 2)), 0.05)
    w = f3.slider("Weight on medicinal importance", 0.0, 1.0, 0.5, 0.1,
                  help="priority = P × ((1 − w) + w × use percentile). Use counts did not predict threat in "
                       "validation, so this weight is a policy choice: how much to favour plants that more "
                       "communities rely on.")
    fams = ["All"] + sorted(df["family"].dropna().unique().tolist())
    fam = f4.selectbox("Family", fams)
    q = df[df["assessment_gap"] & (df["p_threatened"] >= min_p)].copy()
    if region.startswith("Includes"):
        q = q[q["native_subcontinent"].astype(bool)]
    elif region.startswith("Endemic"):
        q = q[q["endemic_indian_subcontinent"] == 1]
    if hide_cult:
        q = q[~q["widely_cultivated"]]
    if hide_unknown:
        q = q[~q["native_range_unknown"]]
    if fam != "All":
        q = q[q["family"] == fam]
    q["priority"] = q["p_threatened"] * ((1 - w) + w * q["use_pressure_pct"])
    show = table(q.sort_values("priority", ascending=False), {"priority": "Priority"})
    st.caption(f"{len(show)} species")
    st.dataframe(show, width="stretch", hide_index=True, height=560,
                 column_config={**TABLE_CFG, "Priority": st.column_config.NumberColumn(format="%.2f")})
    st.download_button("Download this list (CSV)", show.to_csv(index=False), "redroot_priority_list.csv")

# ------------------------------------------------------------------ harvest watchlist
with tab_watch:
    ci = blind["auc_use_among_range_safe_ci"]
    st.markdown(
        "**What range-based screening cannot see.** Plants such as jatamansi, sandalwood and guggul are officially "
        "threatened by *harvest-driven population decline* (IUCN criterion A), even though their ranges are large. "
        "Our validation shows that range-based models miss these species. Literature use counts alone cannot tell "
        "which widespread species are declining either (AUC "
        f"{blind['auc_use_among_range_safe']:.2f}, 95% CI {ci[0]:.2f}–{ci[1]:.2f}).")
    wc = M["watchlist_check"]
    st.markdown("So this list makes **no prediction**. It names unassessed species whose range looks safe but whose "
                "profile matches that of harvest-threatened plants: used more than the median species, native to the "
                "Indian subcontinent, not an annual, native to 15 or fewer botanical countries, and mostly recorded "
                "in the wild. For these plants, **trade, market and harvest monitoring** is the way to detect decline.")
    st.caption(f"Exploratory check on IUCN-assessed species: {wc['rate_in_profile']:.0%} of range-safe species "
               f"matching this profile are officially threatened ({wc['threatened_in_profile']} of "
               f"{wc['n_in_profile']}), against {wc['rate_other_range_safe']:.0%} of other range-safe species "
               f"(odds ratio {wc['odds_ratio']:.1f}, Fisher p = {wc['fisher_p']:.3f}). The profile was chosen "
               f"among {wc['variants_tested']} threshold variants, so this p-value is not corrected for multiple "
               "testing. Treat it as supporting evidence, not proof.")
    wl = df[df["harvest_watchlist"]].sort_values("use_records_global", ascending=False)
    st.caption(f"{len(wl)} species")
    st.dataframe(table(wl), width="stretch", hide_index=True, height=520, column_config=TABLE_CFG)
    st.download_button("Download watchlist (CSV)", table(wl).to_csv(index=False), "redroot_harvest_watchlist.csv")

# ------------------------------------------------------------------ species explorer
with tab_sp:
    names = df.sort_values("use_records_global", ascending=False)["accepted_name"].tolist()
    default = names.index("Nardostachys jatamansi") if "Nardostachys jatamansi" in names else 0
    name = st.selectbox("Species", names, index=default)
    s = df[df["accepted_name"] == name].iloc[0]
    a, b = st.columns([1, 1.4])
    with a:
        st.markdown(f"### *{name}*")
        lf = s.get("lifeform") if isinstance(s.get("lifeform"), str) else "life form n/a"
        cl = s.get("climate") if isinstance(s.get("climate"), str) else ""
        st.caption(f"{s['family']} · {lf}{' · ' + cl if cl else ''}")
        code = s["iucn_code"]
        st.markdown(f"**Official IUCN status:** <span style='background:{CAT_COLOR.get(code, '#ccc')};"
                    f"color:#1a1a1a;padding:2px 8px;border-radius:4px'>{code} · {CAT_NAME.get(code, code)}</span>",
                    unsafe_allow_html=True)
        if isinstance(s.get("iucn_source"), str):
            st.caption(f"Assessed by IUCN under the name {s['iucn_source']}. GBIF's accepted name returns "
                       "'Not Evaluated', so we recovered the status through taxonomic reconciliation.")
        if pd.notna(s["p_threatened"]):
            if pd.notna(s.get("p_threatened_oof")):
                st.markdown(f"**Model P(threatened), out-of-fold:** {s['p_threatened_oof']:.2f}. This is an honest "
                            "estimate: the species' plant family was held out when the model was trained.")
            else:
                st.markdown(f"**Model P(threatened):** {s['p_threatened']:.2f} "
                            f"(ensemble 10–90%: {s['p_threatened_lo']:.2f}–{s['p_threatened_hi']:.2f}); "
                            f"screening threshold {T:.2f}")
        else:
            st.markdown("**Model:** not scored, too few native-range records (fewer than 3 occupied cells)")
        st.markdown(f"**Preliminary criterion B (range only):** {s['criterion_b_prelim']}")
        st.markdown(f"**EOO:** {s['eoo_km2']:,.0f} km² · **AOO:** ≥ {s['aoo_km2']:,.0f} km² · "
                    f"**native-range records:** {int(s['n_native'] or 0):,} "
                    f"({(s['frac_native'] if pd.notna(s['frac_native']) else 0):.0%} of all GBIF records)")
        flags = []
        if s["widely_cultivated"]:
            flags.append("Widely cultivated or naturalised: most records lie outside the native range.")
        if s["native_range_unknown"]:
            flags.append("Native range not found in WCVP, so all records were used.")
        if s["harvest_watchlist"]:
            flags.append("On the harvest watchlist: heavily used, and its range looks safe.")
        for f in flags:
            st.warning(f)
        st.markdown(f"**Recorded medicinal-use records (Dr. Duke's):** {int(s['use_records_global'])} "
                    f"({int(s['use_activities_south_asia'])} distinct uses in South Asia)")
        if isinstance(s.get("top_uses"), str):
            st.markdown(f"**Most-recorded traditional uses** (as documented in literature, not verified efficacy): "
                        f"{s['top_uses']}")
        if isinstance(s.get("sa_communities"), str):
            st.caption(f"Regions and communities as recorded in the literature: {s['sa_communities']}")
    with b:
        sp_pts = pts[pts["speciesKey"] == s["speciesKey"]]
        if len(sp_pts):
            fig = px.scatter_map(sp_pts, lat="lat", lon="lon", color="last_year", zoom=3, height=520,
                                 map_style="carto-positron", color_continuous_scale="Viridis",
                                 hover_data={"records": True, "last_year": True},
                                 labels={"last_year": "Latest record"},
                                 title="Native-range GBIF grid cells with records")
            fig.update_traces(marker=dict(size=7, opacity=0.85))
            fig.update_layout(margin=dict(l=0, r=0, t=30, b=0))
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("No native-range georeferenced records available.")

# ------------------------------------------------------------------ validation
with tab_val:
    st.markdown(f"Trained and tested on **{M['n_train']:,} vascular plants with an official IUCN category** "
                f"({M['n_train_threatened']:,} threatened (CR/EN/VU) vs NT/LC), from {M['n_families']} families: "
                "the IUCN-assessed flora native to the Indian subcontinent, plus every assessed medicinal species "
                f"({M['n_train_medicinal']}, of which {M['n_train_medicinal_threatened']} are threatened). "
                "Cross-validation is **grouped by plant family**, so no family is in both train and test, and it is "
                "repeated over 5 seeds. Medicinal-use data is **not** a model input.")
    rows = []
    for k, lab in [("roc_auc", "ROC-AUC"), ("balanced_accuracy", "Balanced accuracy"),
                   ("sensitivity", "Sensitivity (threatened caught)"), ("specificity", "Specificity"),
                   ("f1_threatened", "F1 (threatened)")]:
        rows.append({"Metric": lab,
                     "Criterion-B rule · regional": M["baseline_all"][k],
                     "RedRoot ML · regional": M["ml_all"][k], "± sd": M["ml_all_sd"][k],
                     "Criterion-B rule · medicinal": M["baseline_medicinal"][k],
                     "RedRoot ML · medicinal": M["ml_medicinal"][k], "± sd ": M["ml_medicinal_sd"][k]})
    vt = pd.DataFrame(rows)
    st.dataframe(vt, hide_index=True, width="stretch", column_config={
        c: st.column_config.NumberColumn(format="%.3f") for c in vt.columns if c != "Metric"})
    at = M["at_threshold"]
    st.caption(f"ML metrics above use a 0.5 cut-off. At the screening threshold of {T:.2f} (maximises sensitivity "
               f"+ specificity on regional out-of-fold predictions): regional sensitivity "
               f"{at['all']['sensitivity']:.2f} / specificity {at['all']['specificity']:.2f}; medicinal "
               f"{at['medicinal']['sensitivity']:.2f} / {at['medicinal']['specificity']:.2f}. "
               f"Ablation: the same model with only the 6 range-size features reaches ROC-AUC "
               f"{M['range_only_auc_mean']:.3f} ± {M['range_only_auc_sd']:.3f}. For the rule baseline, AUC ranks "
               "species by smallness of AOO.")
    c1, c2, c3 = st.columns(3)
    for col, key, title in [(c1, "confusion_baseline_all", "Criterion-B rule (regional)"),
                            (c2, "confusion_ml_all", "RedRoot ML (regional, out-of-fold)")]:
        cm = np.array(M[key])
        fig = go.Figure(go.Heatmap(z=cm, x=["pred. not threatened", "pred. threatened"],
                                   y=["IUCN not threatened", "IUCN threatened"], text=cm, texttemplate="%{text}",
                                   colorscale="Purples", showscale=False))
        fig.update_layout(title=title, height=320, margin=dict(l=0, r=0, t=40, b=0), yaxis_autorange="reversed")
        col.plotly_chart(fig, width="stretch")
    with c3:
        topi = IMP.head(10).iloc[::-1]
        fig = px.bar(topi, x="importance", y="label", orientation="h", error_x="sd",
                     title="Permutation importance (drop in AUC)")
        fig.update_traces(marker_color=ACCENT)
        fig.update_layout(height=320, margin=dict(l=0, r=0, t=40, b=0), yaxis_title=None, xaxis_title=None)
        st.plotly_chart(fig, width="stretch")

    st.subheader("The blind spot: harvest-threatened medicinal plants")
    ci = blind["auc_use_among_range_safe_ci"]
    st.markdown(
        f"At the screening threshold, the model catches **{blind['n_caught']} of {blind['n_threatened_medicinal']}** "
        "officially threatened medicinal species. The ones it catches are mostly narrow-range endemics. The "
        f"**{blind['n_missed']} it misses** are widespread and far more heavily used: median "
        f"{blind['median_use_missed']:.0f} vs {blind['median_use_caught']:.0f} recorded uses (Mann-Whitney "
        f"p = {blind['mannwhitney_p']:.3f}). Their listings rest on harvest-driven decline (IUCN criterion A), "
        "which occurrence data cannot measure. We also tested whether use counts could fill the gap. Among species "
        f"that look safe by range, use records do not separate threatened from non-threatened (AUC "
        f"{blind['auc_use_among_range_safe']:.2f}, 95% CI {ci[0]:.2f}–{ci[1]:.2f}). That is why RedRoot reports "
        "the **harvest watchlist** separately, as a monitoring list, not a prediction.")
    st.caption("Missed examples: " + ", ".join(blind["missed_examples"]))

# ------------------------------------------------------------------ methods
with tab_meth:
    st.markdown((Path(__file__).parent / "docs" / "methods.md").read_text(encoding="utf-8"))
