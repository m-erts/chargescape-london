---
id: census_imd
title: English Indices of Deprivation 2025 (IoD2025), File 7 - all ranks, scores, deciles and population denominators, London LSOA 2021
provider: Ministry of Housing, Communities and Local Government (MHCLG)
url: https://www.gov.uk/government/statistics/english-indices-of-deprivation-2025
download_url: https://assets.publishing.service.gov.uk/media/691ded56d140bbbaa59a2a7d/File_7_IoD2025_All_Ranks_Scores_Deciles_Population_Denominators.csv
licence: OGL v3
status: observed
retrieved: 2026-09-10
size_mb: 9.9 raw CSV (33,755 England LSOAs) / 1.0 interim (4,994 London LSOAs)
spatial_unit: LSOA 2021
temporal: static; published 30 October 2025 (corrected files 17 November 2025); indicator reference periods vary by domain (see the IoD2025 technical report)
script: src/chargescape/data/census.py
raw_path: data/raw/census/imd/
---

## What it is
The 2025 release of the English Indices of Deprivation is the first on **LSOA 2021** geography, so it joins the
Census 2021 layer directly - no 2011 -> 2021 best-fit lookup and no "IMD2019 on old boundaries" caveat is
needed. File 7 contains, for each of England's 33,755 LSOAs, the score / rank / decile of the overall IMD, the
seven domains (income, employment, education skills and training, health deprivation and disability, crime,
barriers to housing and services, living environment), the IDACI / IDAOPI supplementary indices, the six
sub-domains, and the mid-2022 population denominators. `fetch_imd()` filters to the London LSOA list and adds
London-relative `imd_rank_london` (1 = most deprived of 4,994) and `imd_decile_london`.

Output: `data/interim/census/imd2025_lsoa21_london.parquet` (4,994 rows x 58 columns). The feature table
`lsoa21_london_features.parquet` carries the score / rank / decile triplets of the IMD, every domain and
IDACI / IDAOPI (30 columns) plus the two London-relative columns.

## Fields used
Renamed from the long ONS headers: `lsoa21cd`, `lsoa21nm`, `lad24cd`, `lad24nm`, `imd_score`, `imd_rank`,
`imd_decile`, `income_*`, `employment_*`, `education_*`, `health_*`, `crime_*`, `barriers_*`, `living_env_*`,
`idaci_*`, `idaopi_*` (`*` = score | rank | decile), sub-domains (`children_and_young_people_sub_domain_*`,
`adult_skills_sub_domain_*`, `geographical_barriers_sub_domain_*`, `wider_barriers_sub_domain_*`,
`indoors_sub_domain_*`, `outdoors_sub_domain_*`), `total_population_mid_2022`,
`dependent_children_aged_0_15_mid_2022`, `older_population_aged_60_and_over_mid_2022`,
`working_age_population_18_66_for_use_with_employment_deprivation_domain_mid_2022`, `imd_rank_london`,
`imd_decile_london`.

## Known issues / caveats
- Ranks and deciles are **England-wide** (1 = most deprived). London's distribution is compressed in the middle
  (mean England decile 5.0, London LSOA IMD ranks 238-33,741), hence the London-relative rank / decile columns.
- The IMD is a relative measure; scores are not comparable across releases (IoD2019 -> IoD2025) and a change in
  rank does not imply a change in absolute conditions.
- Domain scores have different units (income and employment are rates; others are standardised composites).
- MHCLG re-issued Files 1-9 on 17 November 2025 after ONS corrected an LSOA -> LAD lookup; the data values did
  not change. The file's `lad24cd` matches the ONS lookup's `lad22cd` for all 4,994 London LSOAs.
- One source header is truncated in the CSV ("...10% of LSO"); the renamer tolerates the missing bracket.

## How to reproduce
```bash
PYTHONPATH=src python -m chargescape.data.census        # fetch_imd() downloads File 7 once (cached), filters to London
```
