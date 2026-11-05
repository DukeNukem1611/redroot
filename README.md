# 🌿 RedRoot: extinction-risk radar for South Asia's medicinal plants

**EthnoHack 2026 · Track 3: Biodiversity & Sustainability**

> South Asian traditional medicine uses well over a thousand recorded plant species. Most of them have **never been assessed** for extinction risk, and the gap is widest for the plants with the most recorded uses. RedRoot combines open ethnobotanical, taxonomic and biodiversity data with a validated machine-learning model to show **which medicinal plants most urgently need a Red List assessment and field survey**.

<!-- RESULTS_START -->
_Results are filled in from `data/processed/metrics.json` after running the pipeline._
<!-- RESULTS_END -->

## The problem
- Wild harvest supplies most of the medicinal plant trade in India and the Himalaya. Species such as *Nardostachys jatamansi* (jatamansi) and *Picrorhiza kurroa* (kutki) are already threatened by overharvesting.
- The IUCN Red List is the global standard for extinction risk, but a full assessment takes expert time. Most plants, medicinal ones included, have never been assessed. **No assessment means no visibility in conservation policy, trade regulation (CITES) or funding.**
- Assessors and conservation agencies need to know **where to look first**.

## Our approach
```
Dr. Duke's ethnobotany (CC0) ──► 1,319 medicinal species used in South Asia
        │                                     │ GBIF taxonomy (synonyms merged)
        ▼                                     ▼
 use-pressure features          IUCN category (GBIF mirror) ─► labels
                                GBIF occurrences (map grid)  ─► Kew WCVP native range filter
                                                              ─► EOO, AOO, sampling, recency
                                                                     │
          criterion-B rule baseline ◄──────────┬──────────► gradient-boosted model
                                               │   family-grouped cross-validation
                                               ▼
                     P(threatened) ± uncertainty for unassessed species
                                               ▼
                 priority list = risk × medicinal-use pressure  ─► Streamlit dashboard
```
Full method, limitations and responsible-use notes: [docs/methods.md](docs/methods.md).

## Run the dashboard (2 minutes)
The processed outputs are committed, so the app runs without re-downloading anything:
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Reproduce from scratch (~1 h, mostly downloads)
```bash
cd src
python s00_download.py   # Dr. Duke's, Kew WCVP, TDWG regions (~150 MB)
python s01_species.py            # medicinal species list + GBIF name matching
python s01b_training_species.py  # regional IUCN-assessed flora (training set)
python s02_gbif.py               # IUCN categories, GBIF facets, gridded occurrences (resumable, cached)
python s02b_iucn_synonyms.py     # recover IUCN status hidden behind synonyms (homotypic only)
python s03_features.py           # native-range filter + range metrics
python s04_model.py              # baseline, ML, cross-validation, blind-spot test, predictions
```
API responses are cached in `data/cache/`, so reruns are deterministic and work offline. GBIF data changes over time, so a fresh run on a later date can differ slightly.

## Repository layout
| Path | Contents |
|---|---|
| `src/` | pipeline steps `s00`–`s04`, shared helpers in `common.py` |
| `app.py` | Streamlit dashboard |
| `data/interim/` | species list, name matching audit, IUCN categories, GBIF counts |
| `data/processed/` | `features.csv`, `predictions.csv`, `metrics.json`, `importance.csv`, `points.csv.gz` |
| `docs/` | methods, slides, pitch-video script |

## Data sources and licences
| Dataset | Use | Licence / terms |
|---|---|---|
| [Dr. Duke's Phytochemical and Ethnobotanical Databases](https://doi.org/10.15482/USDA.ADC/1239279), USDA-ARS | medicinal-use records | CC0 1.0 |
| [GBIF Backbone Taxonomy](https://doi.org/10.15468/39omei) | name resolution | CC BY 4.0 |
| [GBIF occurrence data](https://www.gbif.org) via the Maps and Occurrence APIs | species distributions | CC0 / CC BY / CC BY-NC per dataset. Aggregated grid counts are used and no individual records are redistributed. A citable GBIF download DOI will be added for the final version |
| [IUCN Red List](https://www.iucnredlist.org) categories, via GBIF's mirror of the IUCN checklist | training labels | IUCN Terms of Use: non-commercial research use with attribution. Categories are shown, assessments are not redistributed |
| [World Checklist of Vascular Plants](https://doi.org/10.1038/s41597-021-00997-6) (Govaerts et al. 2021), RBG Kew | native ranges, life form, climate | CC BY 4.0 |
| [TDWG World Geographical Scheme for Recording Plant Distributions](https://github.com/tdwg/wgsrpd), level 3 | botanical-country polygons | open (TDWG) |

**Citations:** Duke, J.A. (1992–2016) Dr. Duke's Phytochemical and Ethnobotanical Databases. USDA-ARS. · GBIF.org (2026) GBIF Occurrence Data, accessed 5 Nov 2026. · IUCN (2026) The IUCN Red List of Threatened Species. · Govaerts R. et al. (2021) The World Checklist of Vascular Plants. *Scientific Data* 8:215. · Brummitt R.K. (2001) World Geographical Scheme for Recording Plant Distributions, 2nd ed. TDWG.

## Responsible use
RedRoot's outputs are **preliminary, screening-level estimates** for prioritising expert assessment. They are not official IUCN categories. Recorded traditional uses are shown as documented in the literature, **not as evidence of efficacy or safety**, and nothing here is medical advice. See [docs/methods.md](docs/methods.md#responsible-use-of-traditional-knowledge) for how the tool treats traditional knowledge and community rights.

## Licence
Code: MIT. Derived data: subject to the licences of the source datasets above.
