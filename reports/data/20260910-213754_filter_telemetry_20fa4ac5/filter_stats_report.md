# Telemetry pipeline - filtering

| field | value |
| --- | --- |
| run_id | 20260910-213754_filter_telemetry_20fa4ac5 |
| stage | filter |
| config | configs/data/telemetry_v1.yaml |
| config_hash | 20fa4ac5 |
| git_sha | 4aff202e3ef865531e6b712c056cbf7d962da613 |
| created_at (UTC) | 2026-09-10T21:37:54+00:00 |

## Rows

| step | in | out | dropped | retained |
| --- | --- | --- | --- | --- |
| filter | 15,098,472 | 14,891,540 | 206,932 | 98.63% |

## Thresholds applied

| field | value |
| --- | --- |
| min_channel_nonnull_frac | 0.5 |
| min_turbine_year_nonnull_frac | 0.3 |
| segment_break_steps | 6 |
| min_segment_steps | 144 |

## Channels kept and dropped

| channel | non-null | kept |
| --- | --- | --- |
| ambient_temp_c | 97.67% | yes |
| gearbox_bearing_temp_c | 29.65% | yes |
| gearbox_oil_temp_c | 91.18% | yes |
| generator_bearing_temp_c | 63.67% | yes |
| generator_speed_rpm | 98.04% | yes |
| generator_winding_temp_c | 91.24% | yes |
| main_bearing_temp_c | 88.28% | yes |
| nacelle_position_deg | 70.87% | yes |
| nacelle_temp_c | 62.94% | yes |
| pitch_angle_deg | 91.20% | yes |
| power_kw | 98.82% | yes |
| rotor_speed_rpm | 97.47% | yes |
| wind_direction_deg | 61.12% | yes |
| wind_speed_ms | 98.79% | yes |

## Segments

| field | value |
| --- | --- |
| segments found | 1,931 |
| segments kept | 1,656 |
| segments dropped (too short) | 275 |
| rows dropped (unsegmented or short) | 206,932 |

## Segment length (grid steps)

| segment length statistic | value |
| --- | --- |
| count | 1,931 |
| mean | 7,720 |
| std | 9,431 |
| min | 1 |
| p1 | 1 |
| p5 | 15 |
| p25 | 872 |
| p50 | 4,244 |
| p75 | 1.106e+04 |
| p95 | 2.669e+04 |
| p99 | 4.25e+04 |
| max | 5.256e+04 |
