# RedRoot: an extinction-risk radar for South Asia's medicinal plants

**Track:** 3 · Biodiversity & Sustainability

**Live site:** https://dukenukem1611.github.io/redroot/ · **Code:** https://github.com/DukeNukem1611/redroot

## Short description
RedRoot combines open ethnobotanical, taxonomic and biodiversity data with a family-validated machine-learning model. It shows which of South Asia's 1,319 recorded medicinal plants most urgently need an IUCN Red List assessment, and it exposes the blind spot that hides harvest-threatened species.

## Problem statement
Traditional medicine in South Asia depends on wild-harvested plants, and several of them are already threatened by overharvesting: jatamansi, kuth, kutki. Yet **60% of the 1,319 medicinal species** with recorded uses in the region have no usable IUCN Red List assessment. An unassessed species is invisible to Red List-based policy, trade regulation and conservation funding. Full assessments need scarce expert time, so assessors need to know where to look first.

## Solution / approach
1. **Species list:** every plant with a South Asian ethnobotanical record in Dr. Duke's database (82,873 use records), resolved against the GBIF Backbone Taxonomy.
2. **Taxonomic reconciliation of IUCN status:** we recovered 45 assessments hidden behind GBIF synonyms, 6 of them threatened. Status is transferred only from homotypic synonyms. We reject heterotypic ones: a naive rule would make ashwagandha Critically Endangered via a Cape Verde endemic.
3. **Native-range filter:** GBIF occurrences, gridded at about 2.4 km, are kept only inside each species' native range from Kew's WCVP. For Madagascar periwinkle, 99% of records lie outside its native range.
4. **Features:** IUCN criterion-B range metrics (EOO, AOO), sampling effort and recency, life form and climate. Medicinal-use data is deliberately not a model input.
5. **Model:** gradient-boosted trees trained on 1,619 IUCN-assessed plants native to the Indian subcontinent, compared against the standard criterion-B rule.
6. **Validation:** 5-fold cross-validation grouped by plant family, repeated over 5 seeds. Ablation, screening threshold chosen on out-of-fold data, bootstrap ensemble for uncertainty.
7. **Outputs:** a priority list for assessors, a separate harvest watchlist for trade monitoring, and an interactive website (https://dukenukem1611.github.io/redroot/) with a hotspot map, filterable lists and a species explorer.

## Technologies used
Python, pandas, scikit-learn (HistGradientBoosting), shapely, pyproj, mapbox-vector-tile, SciPy, GBIF REST and Maps APIs. Website: HTML/CSS/JavaScript, Leaflet, D3.js, GitHub Pages.

## Data sources
Dr. Duke's Phytochemical and Ethnobotanical Databases (USDA-ARS, CC0) · GBIF occurrence data and Backbone Taxonomy · IUCN Red List categories via GBIF · Kew World Checklist of Vascular Plants (CC BY 4.0) · TDWG WGSRPD level 3. Full citations and licences are in the README.

## Results
- Validation on 1,619 assessed species: ROC-AUC **0.912 ± 0.004**, against 0.884 for the criterion-B rule. Specificity rises from **0.27 to 0.86** at a sensitivity of 0.83.
- Medicinal subset: ROC-AUC **0.834 ± 0.013** vs 0.812.
- **103** unassessed medicinal species screened as likely threatened (90 native to the subcontinent).
- **51** species on the harvest watchlist.
- **Blind-spot finding:** range-based screening misses the most heavily used threatened plants, with a median of 15.5 vs 4 recorded uses (p = 0.03), including jatamansi, kuth, sandalwood and guggul. Use counts alone cannot fix this (AUC 0.55). We report it openly and handle it with a separate monitoring list.

## Team
- Harshil Agarwal, IIT Kharagpur
- Aditi Choudhary, IIT Kharagpur

## Impact and future development
RedRoot gives Red List assessors (such as the IUCN SSC Medicinal Plant Specialist Group), the Botanical Survey of India, State Biodiversity Boards, the National Medicinal Plants Board and herbal supply chains a transparent, reproducible starting point. Next steps: add CITES trade and market data so the watchlist can detect decline directly; field-check the top priority species; add climate exposure for Himalayan species; and co-design with harvesting communities under the Nagoya Protocol and India's Biological Diversity Act.

## Responsible research
Outputs are preliminary screening estimates, not official Red List categories. Recorded uses are shown as documented in the literature, not as evidence of efficacy or safety. We use only published, openly licensed records, aggregated to counts. The limitations (label bias, sampling bias, the criterion-A blind spot and grid resolution) are documented in the app and in docs/methods.md.

## Gallery images (upload in this order)
1. `gallery/00_cover.png`: cover and thumbnail
2. `gallery/01_hero.png`: headline numbers
3. `gallery/02_findings.png`: the two findings
4. `gallery/03_blind_spot_chart.png`: range vs demand chart
5. `gallery/04_hotspot_map.png`: hotspot map
6. `gallery/05_priority_list.png`: priority list
7. `gallery/06_species_kuth.png`: species explorer (kuth)
8. `gallery/07_harvest_watchlist.png`: harvest watchlist
9. `gallery/08_validation.png`: validation
