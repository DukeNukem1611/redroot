# RedRoot dataset description

This page describes every dataset RedRoot uses, how it was processed, and the datasets RedRoot produces. Every source is open and every step can be re-run from scratch with the scripts in `src/` (see the README section "Reproduce from scratch"). Data were accessed on 5 Nov 2026.

## 1. Summary
| | |
|---|---|
| Question the data answers | Which South Asian medicinal plants are likely threatened with extinction but have never been assessed by the IUCN Red List? |
| Unit of analysis | One accepted plant species (GBIF Backbone Taxonomy) |
| Medicinal species | **1,319** species in 187 families, with 6,429 South Asian use records |
| Labelled training species | **1,619** IUCN-assessed vascular plants native to the Indian subcontinent (432 threatened, 195 families, 512 of them medicinal) |
| Occurrence data | About 20 million georeferenced GBIF records, aggregated to 1,243,567 native-range grid cells for 1,283 medicinal species |
| Personal data | None. All sources describe plants, not people |
| Raw download size | About 550 MB, plus a cache of API responses |

## 2. Source datasets
| Dataset | Provider | What RedRoot takes from it | Licence |
|---|---|---|---|
| [Dr. Duke's Phytochemical and Ethnobotanical Databases](https://doi.org/10.15482/USDA.ADC/1239279) | USDA Agricultural Research Service | The `ETHNOBOT` table (82,873 use records worldwide): plant name, recorded use, country or community, literature reference | CC0 1.0 |
| [GBIF Backbone Taxonomy](https://doi.org/10.15468/39omei) | Global Biodiversity Information Facility | Resolving names to accepted species; synonyms | CC BY 4.0 |
| [GBIF occurrence data](https://www.gbif.org) via the Maps API | GBIF and its publishing institutions | Where each species has been recorded, as gridded counts with the year of the latest record | CC0 / CC BY / CC BY-NC per dataset; only aggregated counts are used |
| [IUCN Red List](https://www.iucnredlist.org) categories, via GBIF's mirror of the IUCN checklist | IUCN | The official extinction-risk category of each assessed species (the training labels) | IUCN Terms of Use: non-commercial use with attribution |
| [World Checklist of Vascular Plants (WCVP)](https://doi.org/10.1038/s41597-021-00997-6) | Royal Botanic Gardens, Kew | Native range by botanical country, life form, climate zone, accepted names | CC BY 4.0 |
| [TDWG WGSRPD, level 3](https://github.com/tdwg/wgsrpd) | Biodiversity Information Standards (TDWG) | Polygons of the botanical countries used to decide whether a grid cell is in a species' native range | Open |

## 3. How the data were processed
1. **Medicinal species list.** All `ETHNOBOT` records whose country field names India (including named Indian communities), Nepal, Pakistan, Bangladesh, Sri Lanka, Bhutan, Sikkim, Kashmir, Assam or the Himalaya. This gives 1,560 distinct plant binomials.
2. **Name resolution.** Each binomial is matched strictly to the GBIF Backbone (confidence ≥ 90, kingdom Plantae). 1,397 binomials matched and were merged into **1,319 accepted species**; 163 could not be matched. Every match and non-match is logged in `data/interim/name_matching.csv`.
3. **IUCN labels.** Each accepted species gets its IUCN category from GBIF. For species that came back unassessed, we also checked their GBIF synonyms and their Kew WCVP accepted name. A category is transferred only from a homotypic synonym (same species epithet, so the same taxon) or the WCVP accepted species. This recovered **45** assessments; 22 unsafe candidates were rejected and logged in `data/interim/iucn_reconciled.csv`.
4. **Occurrences.** GBIF Maps API vector tiles give gridded record counts (about 2.4 km cells for most species). Records with geospatial issues, living garden specimens and fossils are excluded.
5. **Native-range filter.** Each grid cell is assigned to a TDWG botanical country. Only cells inside the species' WCVP native range are kept, which removes cultivated, introduced and naturalised records.
6. **Features.** For each species, 30 model features: range size (extent of occurrence, area of occupancy, occupied 10 km and 50 km cells), geography (latitude, longitude, spans, number of native botanical countries), sampling effort and recency (record counts, share of specimens, year of the latest record), and WCVP life form and climate. Medicinal-use counts are **not** model features; they are used only to rank results.

## 4. Labels and training set
- **Label:** threatened (IUCN CR, EN or VU) = 1; not threatened (NT or LC) = 0. Data Deficient, Not Evaluated and Extinct in the Wild species are not used for training.
- **Why the training set is larger than the medicinal list:** only 43 assessed medicinal species are threatened, too few to train a model. The training set therefore adds every IUCN-assessed vascular plant native to the Indian subcontinent (TDWG region 40) with GBIF records in South Asia, medicinal or not. Least Concern species are randomly sampled rather than taken as the most-recorded, so the model does not learn "rarely recorded = threatened".
- **Split:** 5-fold cross-validation **grouped by plant family**, repeated over 5 seeds, so every score comes from families the model never saw.

### Medicinal species by IUCN category (after reconciliation)
| Category | NE | DD | LC | NT | VU | EN | CR | EW |
|---|---|---|---|---|---|---|---|---|
| Species | 760 | 31 | 470 | 11 | 20 | 18 | 8 | 1 |

NE (Not Evaluated) and DD (Data Deficient) together make up the 791 species (60%) with no usable assessment. These are the species RedRoot scores.

## 5. Datasets RedRoot produces
| File | Rows | Contents |
|---|---|---|
| `data/processed/predictions.csv` | 1,319 | One row per medicinal species: IUCN category and its source, range metrics, P(threatened) with a 10th–90th percentile band, preliminary criterion-B category, priority score, use-pressure percentile and flags |
| `data/processed/features.csv` | 4,108 | The feature table for the medicinal and training species |
| `data/processed/points.csv.gz` | 1,243,567 | Native-range grid cells for medicinal species: latitude, longitude, record count, year of latest record |
| `data/processed/metrics.json` | — | Every reported number: validation, blind-spot test, watchlist check, assessment-gap statistics |
| `data/processed/importance.csv` | 30 | Permutation importance of each feature on held-out families |
| `data/interim/name_matching.csv` | 1,560 | Audit of every name match |
| `data/interim/iucn_reconciled.csv` | 836 | Recovered IUCN categories and rejected synonym candidates |
| `docs/data/*.json` | — | The same results, exported for the website |

## 6. Known biases and limits
- **Label bias.** IUCN-assessed species are not a random sample of plants: threatened and well-studied groups are over-represented.
- **Sampling bias.** GBIF coverage of South Asia is uneven and herbarium-heavy, so under-collected species can look rarer than they are. The sampling-effort features reduce this but cannot remove it.
- **Use counts are not harvest volumes.** They count how often a plant is recorded as medicinal in the literature, not how much is collected from the wild.
- **Grid resolution.** For very widespread species GBIF returns coarser grids, so area of occupancy is a loose lower bound. These species are far above every threat threshold anyway.
- **Taxonomy changes.** GBIF, WCVP and IUCN sometimes disagree on names. The reconciliation step handles the common cases and logs every decision.

## 7. Privacy, ethics and licensing
- There is no personal or sensitive data. No individual GBIF occurrence records are redistributed; only aggregated grid counts are published.
- Traditional knowledge is used only as published in an openly licensed (CC0) database, aggregated to counts and use categories. No preparations, dosages or community-specific knowledge are published beyond what the source cites.
- IUCN categories are shown with attribution; IUCN assessment texts are not redistributed.
- Recorded uses are not evidence of efficacy or safety.
