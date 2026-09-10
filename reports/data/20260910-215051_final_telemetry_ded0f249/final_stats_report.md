# Telemetry pipeline - final

| field | value |
| --- | --- |
| run_id | 20260910-215051_final_telemetry_ded0f249 |
| stage | final |
| config | configs/data/telemetry_v2.yaml |
| config_hash | ded0f249 |
| git_sha | 4aff202e3ef865531e6b712c056cbf7d962da613 |
| created_at (UTC) | 2026-09-10T21:50:51+00:00 |

## Rows

| step | in | out | dropped | retained |
| --- | --- | --- | --- | --- |
| final | 14,891,540 | 14,891,540 | 0 | 100.00% |

## Imputation (each channel carries a companion mask column, ADR-0006)

| channel | steps imputed | share of rows |
| --- | --- | --- |
| ambient_temp_c | 2,185 | 0.015% |
| gearbox_bearing_temp_c | 516 | 0.003% |
| gearbox_oil_temp_c | 2,268 | 0.015% |
| generator_bearing_temp_c | 1,813 | 0.012% |
| generator_speed_rpm | 2,475 | 0.017% |
| generator_winding_temp_c | 2,018 | 0.014% |
| main_bearing_temp_c | 1,824 | 0.012% |
| nacelle_position_deg | 1,907 | 0.013% |
| nacelle_temp_c | 2,079 | 0.014% |
| pitch_angle_deg | 2,256 | 0.015% |
| power_kw | 1,934 | 0.013% |
| rotor_speed_rpm | 1,967 | 0.013% |
| wind_direction_deg | 1,816 | 0.012% |
| wind_speed_ms | 2,476 | 0.017% |

## Split assignment

| split | rows | share |
| --- | --- | --- |
| test | 9,109,996 | 61.18% |
| train | 4,738,594 | 31.82% |
| val | 1,042,950 | 7.00% |

## Splits: windows and events per split

| field | value |
| --- | --- |
| held out (every row test) | hill_of_towie |
| evaluation only (every row test) | care |
| train up to | 2020-12-31T23:59:59Z |
| val up to | 2021-12-31T23:59:59Z |
| after that | test |
| window | 144 steps of context ending at t, stride 1; the horizon (t, t + H] inside t's split |
| segments checked: none spans two splits | 1,656 |
| windows checked: no context or horizon crosses a split boundary | 43,956,756 |

Segments are cut where the split changes, and every window is re-checked from its timestamps alone: the split at its first context step and at the end of its horizon must equal the split at t. A violation stops the stage (`windows.LeakageError`), so the counts above are of windows that passed.

**Narrow label**

| split | source | rows | segments | narrow events | windows 1h | positive 1h | windows 6h | positive 6h | windows 24h | positive 24h |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| train | kelmarsh | 1,527,681 | 294 | 265 | 1,485,603 | 1,197 (0.08%) | 1,485,423 | 6,091 (0.41%) | 1,484,775 | 23,460 (1.58%) |
| train | penmanshiel | 3,210,913 | 502 | 875 | 3,139,043 | 3,874 (0.12%) | 3,138,623 | 20,068 (0.64%) | 3,137,111 | 76,717 (2.45%) |
| val | kelmarsh | 311,215 | 38 | 39 | 305,745 | 137 (0.04%) | 305,565 | 819 (0.27%) | 304,917 | 3,894 (1.28%) |
| val | penmanshiel | 731,735 | 58 | 295 | 723,357 | 1,672 (0.23%) | 722,937 | 5,826 (0.81%) | 721,425 | 17,765 (2.46%) |
| test | care | 5,240,630 | 427 | 45 | 5,179,005 | 270 (0.01%) | 5,176,185 | 1,620 (0.03%) | 5,166,066 | 6,480 (0.13%) |
| test | hill_of_towie | 2,199,043 | 174 | 693 | 2,172,267 | 3,498 (0.16%) | 2,165,618 | 20,000 (0.92%) | 2,145,678 | 72,939 (3.40%) |
| test | kelmarsh | 941,165 | 97 | 415 | 927,258 | 2,412 (0.26%) | 927,078 | 10,588 (1.14%) | 926,430 | 34,065 (3.68%) |
| test | penmanshiel | 729,158 | 66 | 333 | 719,636 | 1,841 (0.26%) | 719,216 | 8,763 (1.22%) | 717,856 | 29,695 (4.14%) |

**Broad label**

| split | source | rows | segments | broad events | windows 1h | positive 1h | windows 6h | positive 6h | windows 24h | positive 24h |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| train | kelmarsh | 1,527,681 | 294 | 2,949 | 1,485,603 | 16,876 (1.14%) | 1,485,423 | 97,263 (6.55%) | 1,484,775 | 360,446 (24.28%) |
| train | penmanshiel | 3,210,913 | 502 | 7,675 | 3,139,043 | 43,800 (1.40%) | 3,138,623 | 239,061 (7.62%) | 3,137,111 | 855,951 (27.28%) |
| val | kelmarsh | 311,215 | 38 | 565 | 305,745 | 3,328 (1.09%) | 305,565 | 19,505 (6.38%) | 304,917 | 72,517 (23.78%) |
| val | penmanshiel | 731,735 | 58 | 1,983 | 723,357 | 11,566 (1.60%) | 722,937 | 60,717 (8.40%) | 721,425 | 213,664 (29.62%) |
| test | care | 5,240,630 | 427 | 45 | 5,179,005 | 270 (0.01%) | 5,176,185 | 1,620 (0.03%) | 5,166,066 | 6,480 (0.13%) |
| test | hill_of_towie | 2,199,043 | 174 | 5,753 | 2,174,161 | 33,739 (1.55%) | 2,174,161 | 193,074 (8.88%) | 2,174,161 | 700,424 (32.22%) |
| test | kelmarsh | 941,165 | 97 | 2,090 | 927,258 | 12,277 (1.32%) | 927,078 | 67,354 (7.27%) | 926,469 | 240,246 (25.93%) |
| test | penmanshiel | 729,158 | 66 | 1,998 | 719,636 | 11,563 (1.61%) | 719,216 | 60,306 (8.38%) | 717,982 | 209,898 (29.23%) |

## Outputs

| file | rows |
| --- | --- |
| Kelmarsh_1__2016.parquet | 48,506 |
| Kelmarsh_1__2017.parquet | 51,855 |
| Kelmarsh_1__2018.parquet | 50,775 |
| Kelmarsh_1__2019.parquet | 52,382 |
| Kelmarsh_1__2020.parquet | 52,005 |
| Kelmarsh_1__2021.parquet | 52,059 |
| Kelmarsh_1__2022.parquet | 51,915 |
| Kelmarsh_1__2023.parquet | 52,367 |
| Kelmarsh_1__2024.parquet | 52,471 |
| Kelmarsh_2__2016.parquet | 48,402 |
| Kelmarsh_2__2017.parquet | 52,074 |
| Kelmarsh_2__2018.parquet | 50,760 |
| Kelmarsh_2__2019.parquet | 52,505 |
| Kelmarsh_2__2020.parquet | 52,018 |
| Kelmarsh_2__2021.parquet | 52,049 |
| Kelmarsh_2__2022.parquet | 52,503 |
| Kelmarsh_2__2023.parquet | 52,376 |
| Kelmarsh_2__2024.parquet | 52,608 |
| Kelmarsh_3__2016.parquet | 47,402 |
| Kelmarsh_3__2017.parquet | 51,879 |
| Kelmarsh_3__2018.parquet | 50,629 |
| Kelmarsh_3__2019.parquet | 52,394 |
| Kelmarsh_3__2020.parquet | 51,870 |
| Kelmarsh_3__2021.parquet | 51,578 |
| Kelmarsh_3__2022.parquet | 52,354 |
| Kelmarsh_3__2023.parquet | 52,094 |
| Kelmarsh_3__2024.parquet | 52,472 |
| Kelmarsh_4__2016.parquet | 46,933 |
| Kelmarsh_4__2017.parquet | 51,898 |
| Kelmarsh_4__2018.parquet | 50,772 |
| Kelmarsh_4__2019.parquet | 52,530 |
| Kelmarsh_4__2020.parquet | 52,013 |
| Kelmarsh_4__2021.parquet | 52,048 |
| Kelmarsh_4__2022.parquet | 52,319 |
| Kelmarsh_4__2023.parquet | 52,226 |
| Kelmarsh_4__2024.parquet | 52,298 |
| Kelmarsh_5__2016.parquet | 47,680 |
| Kelmarsh_5__2017.parquet | 52,016 |
| Kelmarsh_5__2018.parquet | 50,775 |
| Kelmarsh_5__2019.parquet | 52,388 |
| Kelmarsh_5__2020.parquet | 51,904 |
| Kelmarsh_5__2021.parquet | 51,458 |
| Kelmarsh_5__2022.parquet | 52,358 |
| Kelmarsh_5__2023.parquet | 52,251 |
| Kelmarsh_5__2024.parquet | 52,192 |
| Kelmarsh_6__2016.parquet | 46,645 |
| Kelmarsh_6__2017.parquet | 51,352 |
| Kelmarsh_6__2018.parquet | 50,775 |
| Kelmarsh_6__2019.parquet | 52,524 |
| Kelmarsh_6__2020.parquet | 52,020 |
| Kelmarsh_6__2021.parquet | 52,023 |
| Kelmarsh_6__2022.parquet | 52,335 |
| Kelmarsh_6__2023.parquet | 52,153 |
| Kelmarsh_6__2024.parquet | 51,873 |
| Penmanshiel_01__2016.parquet | 28,849 |
| Penmanshiel_01__2017.parquet | 52,267 |
| Penmanshiel_01__2018.parquet | 52,471 |
| Penmanshiel_01__2019.parquet | 52,191 |
| Penmanshiel_01__2020.parquet | 49,479 |
| Penmanshiel_01__2021.parquet | 52,386 |
| Penmanshiel_01__2022.parquet | 52,486 |
| Penmanshiel_02__2016.parquet | 28,848 |
| Penmanshiel_02__2017.parquet | 52,211 |
| Penmanshiel_02__2018.parquet | 51,549 |
| Penmanshiel_02__2019.parquet | 52,293 |
| Penmanshiel_02__2020.parquet | 49,498 |
| Penmanshiel_02__2021.parquet | 52,388 |
| Penmanshiel_02__2022.parquet | 52,490 |
| Penmanshiel_04__2016.parquet | 28,532 |
| Penmanshiel_04__2017.parquet | 52,300 |
| Penmanshiel_04__2018.parquet | 52,473 |
| Penmanshiel_04__2019.parquet | 52,167 |
| Penmanshiel_04__2020.parquet | 49,543 |
| Penmanshiel_04__2021.parquet | 52,303 |
| Penmanshiel_04__2022.parquet | 52,325 |
| Penmanshiel_05__2016.parquet | 28,290 |
| Penmanshiel_05__2017.parquet | 52,302 |
| Penmanshiel_05__2018.parquet | 52,464 |
| Penmanshiel_05__2019.parquet | 52,117 |
| Penmanshiel_05__2020.parquet | 49,552 |
| Penmanshiel_05__2021.parquet | 52,362 |
| Penmanshiel_05__2022.parquet | 52,382 |
| Penmanshiel_06__2016.parquet | 27,474 |
| Penmanshiel_06__2017.parquet | 52,121 |
| Penmanshiel_06__2018.parquet | 52,119 |
| Penmanshiel_06__2019.parquet | 52,083 |
| Penmanshiel_06__2020.parquet | 49,853 |
| Penmanshiel_06__2021.parquet | 52,332 |
| Penmanshiel_06__2022.parquet | 52,487 |
| Penmanshiel_07__2016.parquet | 30,039 |
| Penmanshiel_07__2017.parquet | 52,299 |
| Penmanshiel_07__2018.parquet | 52,475 |
| Penmanshiel_07__2019.parquet | 50,445 |
| Penmanshiel_07__2020.parquet | 49,743 |
| Penmanshiel_07__2021.parquet | 52,218 |
| Penmanshiel_07__2022.parquet | 51,653 |
| Penmanshiel_08__2016.parquet | 19,287 |
| Penmanshiel_08__2017.parquet | 52,318 |
| Penmanshiel_08__2018.parquet | 52,353 |
| Penmanshiel_08__2019.parquet | 52,342 |
| Penmanshiel_08__2020.parquet | 49,909 |
| Penmanshiel_08__2021.parquet | 52,353 |
| Penmanshiel_08__2022.parquet | 52,492 |
| Penmanshiel_09__2016.parquet | 18,939 |
| Penmanshiel_09__2017.parquet | 52,138 |
| Penmanshiel_09__2018.parquet | 52,216 |
| Penmanshiel_09__2019.parquet | 52,289 |
| Penmanshiel_09__2020.parquet | 49,877 |
| Penmanshiel_09__2021.parquet | 52,349 |
| Penmanshiel_09__2022.parquet | 52,489 |
| Penmanshiel_10__2016.parquet | 18,871 |
| Penmanshiel_10__2017.parquet | 52,301 |
| Penmanshiel_10__2018.parquet | 51,549 |
| Penmanshiel_10__2019.parquet | 52,189 |
| Penmanshiel_10__2020.parquet | 49,764 |
| Penmanshiel_10__2021.parquet | 52,300 |
| Penmanshiel_10__2022.parquet | 52,452 |
| Penmanshiel_11__2016.parquet | 19,261 |
| Penmanshiel_11__2017.parquet | 52,300 |
| Penmanshiel_11__2018.parquet | 52,313 |
| Penmanshiel_11__2019.parquet | 52,138 |
| Penmanshiel_11__2020.parquet | 49,412 |
| Penmanshiel_11__2021.parquet | 51,790 |
| Penmanshiel_11__2022.parquet | 48,341 |
| Penmanshiel_12__2016.parquet | 19,241 |
| Penmanshiel_12__2017.parquet | 52,286 |
| Penmanshiel_12__2018.parquet | 52,336 |
| Penmanshiel_12__2019.parquet | 52,150 |
| Penmanshiel_12__2020.parquet | 49,676 |
| Penmanshiel_12__2021.parquet | 52,351 |
| Penmanshiel_12__2022.parquet | 52,451 |
| Penmanshiel_13__2016.parquet | 18,989 |
| Penmanshiel_13__2017.parquet | 52,294 |
| Penmanshiel_13__2018.parquet | 52,336 |
| Penmanshiel_13__2019.parquet | 52,281 |
| Penmanshiel_13__2020.parquet | 49,361 |
| Penmanshiel_13__2021.parquet | 52,215 |
| Penmanshiel_13__2022.parquet | 52,459 |
| Penmanshiel_14__2016.parquet | 18,460 |
| Penmanshiel_14__2017.parquet | 52,300 |
| Penmanshiel_14__2018.parquet | 52,335 |
| Penmanshiel_14__2019.parquet | 52,148 |
| Penmanshiel_14__2020.parquet | 49,674 |
| Penmanshiel_14__2021.parquet | 52,214 |
| Penmanshiel_14__2022.parquet | 52,206 |
| Penmanshiel_15__2016.parquet | 19,042 |
| Penmanshiel_15__2017.parquet | 52,302 |
| Penmanshiel_15__2018.parquet | 52,327 |
| Penmanshiel_15__2019.parquet | 52,143 |
| Penmanshiel_15__2020.parquet | 49,419 |
| Penmanshiel_15__2021.parquet | 52,174 |
| Penmanshiel_15__2022.parquet | 52,445 |
| T01__2018.parquet | 0 |
| T01__2019.parquet | 52,067 |
| T01__2022.parquet | 0 |
| T01__2023.parquet | 52,510 |
| T02__2018.parquet | 0 |
| T02__2019.parquet | 52,505 |
| T02__2022.parquet | 0 |
| T02__2023.parquet | 52,523 |
| T03__2018.parquet | 0 |
| T03__2019.parquet | 52,505 |
| T03__2022.parquet | 0 |
| T03__2023.parquet | 52,528 |
| T04__2018.parquet | 0 |
| T04__2019.parquet | 52,052 |
| T04__2022.parquet | 0 |
| T04__2023.parquet | 52,530 |
| T05__2018.parquet | 0 |
| T05__2019.parquet | 52,505 |
| T05__2022.parquet | 0 |
| T05__2023.parquet | 51,932 |
| T06__2018.parquet | 0 |
| T06__2019.parquet | 52,367 |
| T06__2022.parquet | 0 |
| T06__2023.parquet | 52,523 |
| T07__2018.parquet | 0 |
| T07__2019.parquet | 52,434 |
| T07__2022.parquet | 0 |
| T07__2023.parquet | 52,084 |
| T08__2018.parquet | 0 |
| T08__2019.parquet | 52,487 |
| T08__2022.parquet | 0 |
| T08__2023.parquet | 52,266 |
| T09__2018.parquet | 0 |
| T09__2019.parquet | 52,505 |
| T09__2022.parquet | 0 |
| T09__2023.parquet | 52,514 |
| T10__2018.parquet | 0 |
| T10__2019.parquet | 52,505 |
| T10__2022.parquet | 0 |
| T10__2023.parquet | 52,516 |
| T11__2018.parquet | 0 |
| T11__2019.parquet | 52,481 |
| T11__2022.parquet | 0 |
| T11__2023.parquet | 52,384 |
| T12__2018.parquet | 0 |
| T12__2019.parquet | 52,509 |
| T12__2022.parquet | 0 |
| T12__2023.parquet | 52,504 |
| T13__2018.parquet | 0 |
| T13__2019.parquet | 52,499 |
| T13__2022.parquet | 0 |
| T13__2023.parquet | 52,240 |
| T14__2018.parquet | 0 |
| T14__2019.parquet | 52,341 |
| T14__2022.parquet | 0 |
| T14__2023.parquet | 52,536 |
| T15__2018.parquet | 0 |
| T15__2019.parquet | 52,499 |
| T15__2022.parquet | 0 |
| T15__2023.parquet | 52,461 |
| T16__2018.parquet | 0 |
| T16__2019.parquet | 52,505 |
| T16__2022.parquet | 0 |
| T16__2023.parquet | 50,356 |
| T17__2018.parquet | 0 |
| T17__2019.parquet | 52,505 |
| T17__2022.parquet | 0 |
| T17__2023.parquet | 52,373 |
| T18__2018.parquet | 0 |
| T18__2019.parquet | 52,385 |
| T18__2022.parquet | 0 |
| T18__2023.parquet | 52,536 |
| T19__2018.parquet | 0 |
| T19__2019.parquet | 52,505 |
| T19__2022.parquet | 0 |
| T19__2023.parquet | 52,213 |
| T20__2018.parquet | 0 |
| T20__2019.parquet | 52,499 |
| T20__2022.parquet | 0 |
| T20__2023.parquet | 52,525 |
| T21__2018.parquet | 0 |
| T21__2019.parquet | 51,776 |
| T21__2022.parquet | 0 |
| T21__2023.parquet | 52,553 |
| farm_a_asset0_dataset0__2022.parquet | 21,265 |
| farm_a_asset0_dataset0__2023.parquet | 33,517 |
| farm_a_asset0_dataset24__2022.parquet | 35,875 |
| farm_a_asset0_dataset24__2023.parquet | 19,061 |
| farm_a_asset0_dataset26__2022.parquet | 11,563 |
| farm_a_asset0_dataset26__2023.parquet | 42,083 |
| farm_a_asset0_dataset71__2022.parquet | 52,231 |
| farm_a_asset0_dataset71__2023.parquet | 2,449 |
| farm_a_asset0_dataset73__2022.parquet | 29,584 |
| farm_a_asset0_dataset73__2023.parquet | 24,391 |
| farm_a_asset10_dataset10__2022.parquet | 12,033 |
| farm_a_asset10_dataset10__2023.parquet | 41,514 |
| farm_a_asset10_dataset17__2022.parquet | 8,836 |
| farm_a_asset10_dataset17__2023.parquet | 46,207 |
| farm_a_asset10_dataset3__2022.parquet | 35,475 |
| farm_a_asset10_dataset3__2023.parquet | 19,981 |
| farm_a_asset10_dataset40__2022.parquet | 52,191 |
| farm_a_asset10_dataset40__2023.parquet | 3,936 |
| farm_a_asset10_dataset42__2022.parquet | 16,288 |
| farm_a_asset10_dataset42__2023.parquet | 37,553 |
| farm_a_asset11_dataset25__2022.parquet | 31,772 |
| farm_a_asset11_dataset25__2023.parquet | 22,877 |
| farm_a_asset11_dataset68__2022.parquet | 22,229 |
| farm_a_asset11_dataset68__2023.parquet | 31,990 |
| farm_a_asset11_dataset69__2022.parquet | 17,222 |
| farm_a_asset11_dataset69__2023.parquet | 37,525 |
| farm_a_asset11_dataset92__2022.parquet | 38,829 |
| farm_a_asset11_dataset92__2023.parquet | 15,175 |
| farm_a_asset13_dataset14__2022.parquet | 43,369 |
| farm_a_asset13_dataset14__2023.parquet | 10,769 |
| farm_a_asset13_dataset38__2022.parquet | 26,542 |
| farm_a_asset13_dataset38__2023.parquet | 28,157 |
| farm_a_asset13_dataset45__2022.parquet | 37,014 |
| farm_a_asset13_dataset45__2023.parquet | 16,664 |
| farm_a_asset13_dataset84__2022.parquet | 17,154 |
| farm_a_asset13_dataset84__2023.parquet | 36,556 |
| farm_a_asset21_dataset13__2022.parquet | 32,803 |
| farm_a_asset21_dataset13__2023.parquet | 20,793 |
| farm_a_asset21_dataset22__2022.parquet | 19,838 |
| farm_a_asset21_dataset22__2023.parquet | 33,084 |
| farm_a_asset21_dataset51__2022.parquet | 12,493 |
| farm_a_asset21_dataset51__2023.parquet | 41,906 |
| farm_a_asset21_dataset72__2022.parquet | 12,040 |
| farm_a_asset21_dataset72__2023.parquet | 42,005 |
| farm_b_asset0_dataset21__2022.parquet | 14,108 |
| farm_b_asset0_dataset21__2023.parquet | 38,964 |
| farm_b_asset11_dataset19__2022.parquet | 47,924 |
| farm_b_asset11_dataset19__2023.parquet | 8,353 |
| farm_b_asset11_dataset74__2022.parquet | 52,394 |
| farm_b_asset11_dataset74__2023.parquet | 3,211 |
| farm_b_asset12_dataset77__2022.parquet | 31,248 |
| farm_b_asset12_dataset77__2023.parquet | 30,529 |
| farm_b_asset12_dataset86__2022.parquet | 35,751 |
| farm_b_asset12_dataset86__2023.parquet | 19,736 |
| farm_b_asset13_dataset2__2022.parquet | 20,908 |
| farm_b_asset13_dataset2__2023.parquet | 33,867 |
| farm_b_asset13_dataset7__2022.parquet | 26,640 |
| farm_b_asset13_dataset7__2023.parquet | 31,249 |
| farm_b_asset14_dataset34__2022.parquet | 18,709 |
| farm_b_asset14_dataset34__2023.parquet | 37,859 |
| farm_b_asset14_dataset52__2022.parquet | 24,757 |
| farm_b_asset14_dataset52__2023.parquet | 30,515 |
| farm_b_asset2_dataset83__2022.parquet | 26,568 |
| farm_b_asset2_dataset83__2023.parquet | 39,579 |
| farm_b_asset5_dataset82__2022.parquet | 14,262 |
| farm_b_asset5_dataset82__2023.parquet | 40,747 |
| farm_b_asset6_dataset23__2022.parquet | 15,159 |
| farm_b_asset6_dataset23__2023.parquet | 39,384 |
| farm_b_asset6_dataset53__2022.parquet | 764 |
| farm_b_asset6_dataset53__2023.parquet | 52,560 |
| farm_b_asset6_dataset53__2024.parquet | 5,284 |
| farm_b_asset7_dataset27__2022.parquet | 17,628 |
| farm_b_asset7_dataset27__2023.parquet | 44,641 |
| farm_b_asset7_dataset87__2022.parquet | 15,474 |
| farm_b_asset7_dataset87__2023.parquet | 39,883 |
| farm_c_asset12_dataset15__2022.parquet | 46,800 |
| farm_c_asset12_dataset15__2023.parquet | 7,633 |
| farm_c_asset12_dataset50__2022.parquet | 8,640 |
| farm_c_asset12_dataset50__2023.parquet | 46,513 |
| farm_c_asset12_dataset66__2022.parquet | 49,392 |
| farm_c_asset12_dataset66__2023.parquet | 4,111 |
| farm_c_asset13_dataset29__2022.parquet | 43,044 |
| farm_c_asset13_dataset29__2023.parquet | 11,821 |
| farm_c_asset14_dataset85__2022.parquet | 49,169 |
| farm_c_asset14_dataset85__2023.parquet | 3,248 |
| farm_c_asset15_dataset64__2022.parquet | 14,397 |
| farm_c_asset15_dataset64__2023.parquet | 40,036 |
| farm_c_asset15_dataset78__2022.parquet | 22,242 |
| farm_c_asset15_dataset78__2023.parquet | 30,904 |
| farm_c_asset16_dataset30__2022.parquet | 2,448 |
| farm_c_asset16_dataset30__2023.parquet | 52,560 |
| farm_c_asset16_dataset30__2024.parquet | 1,103 |
| farm_c_asset16_dataset46__2022.parquet | 33,799 |
| farm_c_asset16_dataset46__2023.parquet | 21,334 |
| farm_c_asset16_dataset65__2022.parquet | 8,614 |
| farm_c_asset16_dataset65__2023.parquet | 47,304 |
| farm_c_asset16_dataset79__2022.parquet | 22,986 |
| farm_c_asset16_dataset79__2023.parquet | 30,295 |
| farm_c_asset21_dataset47__2022.parquet | 1,350 |
| farm_c_asset21_dataset47__2023.parquet | 52,416 |
| farm_c_asset21_dataset47__2024.parquet | 227 |
| farm_c_asset21_dataset62__2022.parquet | 7,998 |
| farm_c_asset21_dataset62__2023.parquet | 45,450 |
| farm_c_asset23_dataset37__2022.parquet | 43,092 |
| farm_c_asset23_dataset37__2023.parquet | 10,621 |
| farm_c_asset23_dataset70__2022.parquet | 7,404 |
| farm_c_asset23_dataset70__2023.parquet | 48,634 |
| farm_c_asset23_dataset80__2022.parquet | 12,371 |
| farm_c_asset23_dataset80__2023.parquet | 42,542 |
| farm_c_asset2_dataset12__2022.parquet | 27,072 |
| farm_c_asset2_dataset12__2023.parquet | 29,035 |
| farm_c_asset2_dataset36__2022.parquet | 19,897 |
| farm_c_asset2_dataset36__2023.parquet | 35,551 |
| farm_c_asset32_dataset59__2022.parquet | 45,504 |
| farm_c_asset32_dataset59__2023.parquet | 9,361 |
| farm_c_asset32_dataset5__2022.parquet | 47,664 |
| farm_c_asset32_dataset5__2023.parquet | 5,131 |
| farm_c_asset33_dataset41__2022.parquet | 49,362 |
| farm_c_asset33_dataset41__2023.parquet | 6,304 |
| farm_c_asset33_dataset49__2022.parquet | 38,880 |
| farm_c_asset33_dataset49__2023.parquet | 14,134 |
| farm_c_asset34_dataset18__2022.parquet | 16,128 |
| farm_c_asset34_dataset18__2023.parquet | 36,720 |
| farm_c_asset34_dataset4__2022.parquet | 22,548 |
| farm_c_asset34_dataset4__2023.parquet | 33,901 |
| farm_c_asset34_dataset56__2022.parquet | 22,573 |
| farm_c_asset34_dataset56__2023.parquet | 30,843 |
| farm_c_asset34_dataset94__2022.parquet | 29,024 |
| farm_c_asset34_dataset94__2023.parquet | 25,841 |
| farm_c_asset35_dataset31__2022.parquet | 50,400 |
| farm_c_asset35_dataset31__2023.parquet | 4,189 |
| farm_c_asset35_dataset48__2022.parquet | 36,360 |
| farm_c_asset35_dataset48__2023.parquet | 18,937 |
| farm_c_asset35_dataset58__2022.parquet | 11,612 |
| farm_c_asset35_dataset58__2023.parquet | 42,821 |
| farm_c_asset35_dataset67__2022.parquet | 48,096 |
| farm_c_asset35_dataset67__2023.parquet | 13,393 |
| farm_c_asset38_dataset6__2022.parquet | 4,327 |
| farm_c_asset38_dataset6__2023.parquet | 50,538 |
| farm_c_asset38_dataset81__2022.parquet | 6,759 |
| farm_c_asset38_dataset81__2023.parquet | 47,173 |
| farm_c_asset42_dataset32__2022.parquet | 13,504 |
| farm_c_asset42_dataset32__2023.parquet | 41,505 |
| farm_c_asset42_dataset91__2022.parquet | 11,751 |
| farm_c_asset42_dataset91__2023.parquet | 44,857 |
| farm_c_asset43_dataset11__2022.parquet | 10,869 |
| farm_c_asset43_dataset11__2023.parquet | 45,568 |
| farm_c_asset43_dataset33__2022.parquet | 18,642 |
| farm_c_asset43_dataset33__2023.parquet | 37,231 |
| farm_c_asset43_dataset61__2022.parquet | 34,704 |
| farm_c_asset43_dataset61__2023.parquet | 20,881 |
| farm_c_asset43_dataset93__2022.parquet | 21,937 |
| farm_c_asset43_dataset93__2023.parquet | 33,936 |
| farm_c_asset44_dataset44__2022.parquet | 21,804 |
| farm_c_asset44_dataset44__2023.parquet | 41,199 |
| farm_c_asset44_dataset75__2022.parquet | 35,213 |
| farm_c_asset44_dataset75__2023.parquet | 20,948 |
| farm_c_asset50_dataset55__2022.parquet | 9,435 |
| farm_c_asset50_dataset55__2023.parquet | 46,318 |
| farm_c_asset50_dataset8__2022.parquet | 18,762 |
| farm_c_asset50_dataset8__2023.parquet | 36,040 |
| farm_c_asset52_dataset28__2022.parquet | 31,458 |
| farm_c_asset52_dataset28__2023.parquet | 24,460 |
| farm_c_asset52_dataset39__2022.parquet | 10,866 |
| farm_c_asset52_dataset39__2023.parquet | 42,861 |
| farm_c_asset52_dataset43__2022.parquet | 20,141 |
| farm_c_asset52_dataset43__2023.parquet | 35,012 |
| farm_c_asset52_dataset54__2022.parquet | 48,184 |
| farm_c_asset52_dataset54__2023.parquet | 7,401 |
| farm_c_asset53_dataset16__2022.parquet | 1,296 |
| farm_c_asset53_dataset16__2023.parquet | 51,264 |
| farm_c_asset53_dataset16__2024.parquet | 1,008 |
| farm_c_asset53_dataset1__2022.parquet | 13,248 |
| farm_c_asset53_dataset1__2023.parquet | 40,321 |
| farm_c_asset53_dataset20__2022.parquet | 24,905 |
| farm_c_asset53_dataset20__2023.parquet | 29,096 |
| farm_c_asset53_dataset35__2022.parquet | 14,544 |
| farm_c_asset53_dataset35__2023.parquet | 38,071 |
| farm_c_asset53_dataset60__2022.parquet | 45,615 |
| farm_c_asset53_dataset60__2023.parquet | 8,818 |
| farm_c_asset53_dataset76__2022.parquet | 50,544 |
| farm_c_asset53_dataset76__2023.parquet | 1,542 |
| farm_c_asset55_dataset57__2022.parquet | 35,966 |
| farm_c_asset55_dataset57__2023.parquet | 19,043 |
| farm_c_asset55_dataset88__2022.parquet | 13,104 |
| farm_c_asset55_dataset88__2023.parquet | 42,337 |
| farm_c_asset55_dataset9__2022.parquet | 21,843 |
| farm_c_asset55_dataset9__2023.parquet | 34,186 |
| farm_c_asset56_dataset63__2022.parquet | 25,781 |
| farm_c_asset56_dataset63__2023.parquet | 29,084 |
| farm_c_asset56_dataset90__2022.parquet | 20,934 |
| farm_c_asset56_dataset90__2023.parquet | 33,946 |
| farm_c_asset5_dataset89__2022.parquet | 42,617 |
| farm_c_asset5_dataset89__2023.parquet | 11,960 |
