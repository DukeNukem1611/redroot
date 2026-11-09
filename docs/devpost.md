# RedRoot: an extinction-risk radar for South Asia's medicinal plants

**Problem statement:** DN-OP-01 · Open Innovation Challenge
**Track:** Sustainability and Environmental Innovation

**Live demo:** https://dukenukem1611.github.io/redroot/ · **Code:** https://github.com/DukeNukem1611/redroot · **Dataset description:** https://github.com/DukeNukem1611/redroot/blob/main/docs/dataset.md

## Elevator pitch (Devpost field, 200 characters max)
60% of South Asia's medicinal plants have never been assessed for extinction risk. RedRoot uses open data and validated ML to show assessors where to look first.

## Project overview
RedRoot combines five open datasets on traditional medicine, plant taxonomy and biodiversity with a machine-learning model validated on plant families it never saw. It shows which of South Asia's 1,319 recorded medicinal plants most urgently need an IUCN Red List assessment, and it exposes a blind spot in standard screening that hides plants threatened by overharvesting.

## Problem statement
Traditional medicine in South Asia depends on wild-harvested plants, and several are already threatened by overharvesting: jatamansi, kuth, kutki. Yet **60% of the 1,319 medicinal species** with recorded uses in the region have no usable IUCN Red List assessment. An unassessed species is invisible to Red List-based policy, trade regulation (CITES) and conservation funding. Each assessment needs scarce expert time, so assessors and agencies need to know where to look first.

## Proposed solution
1. **Species list:** every plant with a South Asian ethnobotanical record in Dr. Duke's database, resolved against the GBIF Backbone Taxonomy.
2. **Recovering hidden assessments:** 45 IUCN assessments, 6 of them threatened, were hidden behind GBIF synonyms. We transfer status only from homotypic synonyms (the same taxon under another genus). A naive rule would make ashwagandha Critically Endangered via a Cape Verde endemic; that and 21 other unsafe transfers are rejected and logged.
3. **Native-range filter:** GBIF occurrences, gridded at about 2.4 km, are kept only inside each species' native range from Kew's WCVP. For Madagascar periwinkle, 99% of records fall outside its native range.
4. **Features:** IUCN criterion-B range metrics (extent of occurrence, area of occupancy), sampling effort and recency, life form and climate. Medicinal-use data is deliberately not a model input.
5. **Model:** gradient-boosted trees trained on 1,619 IUCN-assessed plants native to the Indian subcontinent, compared against the standard criterion-B rule.
6. **Calibration and explanations:** an isotonic map, checked by family-grouped cross-fitting, turns each score into the share of similar assessed species that are threatened, and exact SHAP values show the four factors that drive each species' score.
7. **Two outputs for two kinds of risk:** a **priority list** of unassessed species the model screens as likely threatened, and a separate **harvest watchlist** for species whose range looks safe but whose profile matches the plants range-based screening misses.

## Technology stack
- **Language and analysis:** Python, pandas, NumPy, SciPy
- **Machine learning:** scikit-learn (HistGradientBoostingClassifier, grouped cross-validation, permutation importance, bootstrap ensemble, isotonic calibration), SHAP (TreeSHAP explanations)
- **Geospatial:** shapely, pyproj, mapbox-vector-tile, GBIF Maps API
- **Website:** HTML, CSS and JavaScript, Leaflet, D3.js, hosted on GitHub Pages (no backend)
- **Datasets:** Dr. Duke's Phytochemical and Ethnobotanical Databases (USDA-ARS, CC0), GBIF occurrence data and Backbone Taxonomy, IUCN Red List categories via GBIF, Kew World Checklist of Vascular Plants (CC BY 4.0), TDWG WGSRPD level 3. Details: docs/dataset.md

## Implementation and demonstration
- **Live website:** https://dukenukem1611.github.io/redroot/ with headline numbers, the two findings, a hotspot map, a filterable and downloadable priority list, the harvest watchlist, a species explorer for all 1,319 plants (with the drivers of each score and a printable one-page assessor sheet), validation results and full methods.
- **Code:** an eight-script pipeline (`src/s00` to `src/s05`), reproducible from scratch in about an hour. Every API response is cached so reruns are deterministic.

## Results and validation
- Validated with 5-fold cross-validation **grouped by plant family**, repeated over 5 seeds, so every score comes from families the model never trained on.
- ROC-AUC **0.912 ± 0.004**, against 0.884 for the criterion-B rule.
- At the screening threshold, the criterion-B rule raises **866 false alarms** among 1,187 non-threatened species; RedRoot raises **170** and still catches **83%** of threatened species (357 of 432) (specificity 0.27 → 0.86).
- Medicinal subset: ROC-AUC **0.834 ± 0.013** vs 0.812.
- **Decision value:** working down RedRoot's ranking (out-of-fold), the top 100 assessed species hold **97** threatened ones, against 84 for the range-size rule and about 27 at random. Finding half of the 432 threatened species takes **243** assessments instead of 283 or 810. On medicinal species, the top 50 hold 21 threatened ones, against 15 and about 4.
- **Calibration:** the calibrated share threatened has an expected calibration error of **0.016** (raw score: 0.052).
- **103** unassessed medicinal species screened as likely threatened (90 native to the subcontinent); **51** species on the harvest watchlist.
- **Blind-spot finding:** range-based screening misses the most heavily used threatened plants, with a median of 15.5 vs 4 recorded uses (Mann-Whitney p = 0.03), including jatamansi, kuth, sandalwood and guggul. Use counts alone cannot fix this (AUC 0.55). We report it openly and handle it with the separate watchlist.

## Potential impact
- **Users:** Red List assessors (such as the IUCN SSC Medicinal Plant Specialist Group), the Botanical Survey of India, State Biodiversity Boards, the National Medicinal Plants Board, and herbal-industry supply chains that need to know which raw materials carry risk.
- **Feasibility:** runs on open data and free APIs, needs no API keys, and the website has no backend to maintain.
- **Scalability:** extending to another region means changing only the country list and the botanical region code.
- **Next steps:** add CITES trade and market data so the watchlist can detect decline directly; field-check the top priority species with regional botanists; add climate exposure for Himalayan species; co-design the watchlist with harvesting communities under the Nagoya Protocol and India's Biological Diversity Act.

## Responsible AI and research
Outputs are preliminary screening estimates, not official Red List categories. Recorded uses are shown as documented in the literature, not as evidence of efficacy or safety. We use only published, openly licensed records, aggregated to counts. The limitations (label bias, sampling bias, the blind spot for harvest-driven decline, grid resolution) are documented on the website and in docs/methods.md.

## Team contributions
- **Harshil Agarwal**, IIT Kharagpur: data pipeline (Dr. Duke's, GBIF and WCVP ingestion, name resolution, native-range filter, range metrics), IUCN synonym reconciliation, the machine-learning model and its family-grouped validation, and the website's maps and data export.
- **Aditi Choudhary**, IIT Kharagpur: problem research on the medicinal-plant trade and Red List coverage, the blind-spot analysis and harvest-watchlist design, website design and the species explorer, documentation (methods, dataset description, responsible-use notes) and the presentation.

## Gallery images (upload in this order)
1. `gallery/00_cover.png`: cover and thumbnail
2. `gallery/01_hero.png`: headline numbers
3. `gallery/02_findings.png`: the two findings
4. `gallery/03_blind_spot_chart.png`: range vs demand chart
5. `gallery/04_hotspot_map.png`: hotspot map
6. `gallery/05_priority_list.png`: priority list
7. `gallery/06_species_kuth.png`: species explorer (kuth), with the drivers of its score
8. `gallery/07_harvest_watchlist.png`: harvest watchlist
9. `gallery/08_validation.png`: validation
10. `gallery/09_decision_value.png`: how many threatened species each ranking finds, and calibration
