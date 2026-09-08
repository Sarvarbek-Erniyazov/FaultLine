# Raw inventory: penmanshiel

| field | value |
| --- | --- |
| source | penmanshiel |
| provider | Cubico Sustainable Investments Ltd |
| licence | CC-BY-4.0 |
| zenodo record | 16,807,304 |
| concept DOI | 10.5281/zenodo.5946807 |
| staged directory | C:\Users\sharg\Desktop\github\FaultLine\data\raw\telemetry\penmanshiel |
| files staged | 8 |
| members discovered | 112 |
| generated (UTC) | 2026-09-08T22:56:35+00:00 |
| git_sha | f306e73f6f0231e626d317f26b0a316cffd33d42 |

## Free-text verdict

**VERIFIED no** - messages are present but template-like: at most 73 distinct strings with a mean length of 15.9 characters, which is a controlled vocabulary rather than open-ended language (ADR-0001 holds)

This is the evidence behind ADR-0001: whether the paired text in this record is open-ended language or a controlled vocabulary.

## Staged files

| file | size (MB) | members |
| --- | --- | --- |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip | 128.9 | 18 |
| Penmanshiel_SCADA_2016_WT11-15_3107.zip | 55.9 | 10 |
| Penmanshiel_SCADA_2017_WT01-10_3114.zip | 273.5 | 18 |
| Penmanshiel_SCADA_2017_WT11-15_3115.zip | 152.9 | 10 |
| Penmanshiel_SCADA_2018_WT01-10_3113.zip | 365 | 18 |
| Penmanshiel_SCADA_2018_WT11-15_3116.zip | 204.8 | 10 |
| Penmanshiel_SCADA_2019_WT01-10_3112.zip | 473.5 | 18 |
| Penmanshiel_SCADA_2019_WT11-15_3117.zip | 265.4 | 10 |

## Members by kind

| kind | members | uncompressed (MB) |
| --- | --- | --- |
| scada_10min | 56 | 7,240 |
| status_events | 56 | 33.6 |

## Event tables found

| member | rows | columns | code column | message column | unique codes | unique messages | free-text share | mean chars |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip::Status_Penmanshiel… | 2,698 | 9 | Code | Message | 65 | 65 | 100.0% | 15.6 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip::Status_Penmanshiel… | 1,657 | 9 | Code | Message | 59 | 59 | 100.0% | 15.2 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip::Status_Penmanshiel… | 1,427 | 9 | Code | Message | 71 | 71 | 100.0% | 15.6 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip::Status_Penmanshiel… | 1,500 | 9 | Code | Message | 58 | 58 | 100.0% | 15.5 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip::Status_Penmanshiel… | 1,684 | 9 | Code | Message | 63 | 63 | 100.0% | 15 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip::Status_Penmanshiel… | 1,843 | 9 | Code | Message | 55 | 55 | 100.0% | 15.9 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip::Status_Penmanshiel… | 1,174 | 9 | Code | Message | 62 | 62 | 100.0% | 15.6 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip::Status_Penmanshiel… | 1,321 | 9 | Code | Message | 64 | 64 | 100.0% | 15.3 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip::Status_Penmanshiel… | 1,294 | 9 | Code | Message | 54 | 54 | 100.0% | 15 |
| Penmanshiel_SCADA_2016_WT11-15_3107.zip::Status_Penmanshiel… | 1,025 | 9 | Code | Message | 67 | 67 | 100.0% | 15.7 |
| Penmanshiel_SCADA_2016_WT11-15_3107.zip::Status_Penmanshiel… | 1,086 | 9 | Code | Message | 73 | 73 | 100.0% | 15.5 |
| Penmanshiel_SCADA_2016_WT11-15_3107.zip::Status_Penmanshiel… | 907 | 9 | Code | Message | 41 | 41 | 100.0% | 15 |

### Top messages: Penmanshiel_SCADA_2016_WT01-10_3107.zip::Status_Penmanshiel…

| message | count | share |
| --- | --- | --- |
| Wind < start wind | 1,126 | 43.54% |
| System OK | 936 | 36.19% |
| P output externally reduced | 144 | 5.57% |
| Manual yaw | 50 | 1.93% |
| Brake accumulator defect | 48 | 1.86% |
| Externally stopped | 48 | 1.86% |
| Manual stop - on site | 32 | 1.24% |
| Comm. failure FPM | 30 | 1.16% |
| Absence of wind during run-up | 20 | 0.77% |
| Battery charge cycle axis 1 error | 20 | 0.77% |
| Battery charge cycle axis 2 error | 20 | 0.77% |
| Battery charge cycle axis 3 error | 20 | 0.77% |
| Battery test | 20 | 0.77% |
| High frequency - P reduction | 14 | 0.54% |
| Timeout brake closed | 14 | 0.54% |
| Cable autounwind | 12 | 0.46% |
| Frequency converter not ready | 10 | 0.39% |
| Gearbox warm-up stage | 10 | 0.39% |
| Grid loss | 6 | 0.23% |
| Transient voltage peak | 6 | 0.23% |

### Top messages: Penmanshiel_SCADA_2016_WT01-10_3107.zip::Status_Penmanshiel…

| message | count | share |
| --- | --- | --- |
| Wind < start wind | 696 | 43.99% |
| System OK | 550 | 34.77% |
| P output externally reduced | 70 | 4.42% |
| Externally stopped | 46 | 2.91% |
| Vane 2 defect | 41 | 2.59% |
| Manual stop - on site | 27 | 1.71% |
| Manual yaw | 23 | 1.45% |
| Battery test | 22 | 1.39% |
| Comm. failure FPM | 18 | 1.14% |
| Gear heating enabled | 12 | 0.76% |
| Cable autounwind | 11 | 0.70% |
| Absence of wind during run-up | 10 | 0.63% |
| Timeout brake closed | 9 | 0.57% |
| Frequency converter not ready | 8 | 0.51% |
| Grid loss | 7 | 0.44% |
| Overload generator fan 1 | 7 | 0.44% |
| Repeating error BP52 | 7 | 0.44% |
| Brake accumulator defect | 6 | 0.38% |
| Overload generator fan 2 | 6 | 0.38% |
| Overload generator fan 3 | 6 | 0.38% |

### Top messages: Penmanshiel_SCADA_2016_WT01-10_3107.zip::Status_Penmanshiel…

| message | count | share |
| --- | --- | --- |
| Wind < start wind | 566 | 42.37% |
| System OK | 479 | 35.85% |
| P output externally reduced | 51 | 3.82% |
| Manual stop - on site | 33 | 2.47% |
| Manual yaw | 26 | 1.95% |
| Externally stopped | 24 | 1.80% |
| Battery test | 22 | 1.65% |
| Comm. failure FPM | 21 | 1.57% |
| Low gearbox oil pressure | 18 | 1.35% |
| Absence of wind during run-up | 12 | 0.90% |
| High temp. gen. bearing 1 | 12 | 0.90% |
| Battery charge cycle axis 1 error | 9 | 0.67% |
| Battery charge cycle axis 2 error | 9 | 0.67% |
| Battery charge cycle axis 3 error | 9 | 0.67% |
| Cable autounwind | 8 | 0.60% |
| Frequency converter not ready | 8 | 0.60% |
| Gearbox warm-up stage | 8 | 0.60% |
| Repeating error BP52 | 8 | 0.60% |
| Grid loss | 7 | 0.52% |
| High frequency - P reduction | 6 | 0.45% |

### Top messages: Penmanshiel_SCADA_2016_WT01-10_3107.zip::Status_Penmanshiel…

| message | count | share |
| --- | --- | --- |
| Wind < start wind | 716 | 50.03% |
| System OK | 476 | 33.26% |
| P output externally reduced | 31 | 2.17% |
| Manual stop - on site | 26 | 1.82% |
| Battery test | 19 | 1.33% |
| Externally stopped | 17 | 1.19% |
| Manual yaw | 16 | 1.12% |
| Absence of wind during run-up | 15 | 1.05% |
| Comm. failure FPM | 15 | 1.05% |
| Repeating error BP52 | 12 | 0.84% |
| Cable autounwind | 11 | 0.77% |
| Missing gear oil (high rpm) | 11 | 0.77% |
| Battery charge cycle axis 1 error | 10 | 0.70% |
| Battery charge cycle axis 2 error | 10 | 0.70% |
| Battery charge cycle axis 3 error | 10 | 0.70% |
| Frequency converter not ready | 8 | 0.56% |
| Gearbox warm-up stage | 8 | 0.56% |
| Max. wind speed | 7 | 0.49% |
| Timeout brake closed | 7 | 0.49% |
| Grid loss | 6 | 0.42% |

### Top messages: Penmanshiel_SCADA_2016_WT01-10_3107.zip::Status_Penmanshiel…

| message | count | share |
| --- | --- | --- |
| Wind < start wind | 537 | 33.60% |
| System OK | 478 | 29.91% |
| Vane 2 defect | 326 | 20.40% |
| P output externally reduced | 50 | 3.13% |
| Externally stopped | 32 | 2.00% |
| Comm. failure FPM | 22 | 1.38% |
| Battery test | 19 | 1.19% |
| Manual yaw | 17 | 1.06% |
| Manual stop - on site | 16 | 1.00% |
| Timeout brake closed | 12 | 0.75% |
| Brake accumulator defect | 11 | 0.69% |
| Absence of wind during run-up | 10 | 0.63% |
| Pitch measuring system 1><2 | 10 | 0.63% |
| Battery charge cycle axis 1 error | 9 | 0.56% |
| Battery charge cycle axis 2 error | 9 | 0.56% |
| Battery charge cycle axis 3 error | 9 | 0.56% |
| Cable autounwind | 9 | 0.56% |
| Gearbox warm-up stage | 9 | 0.56% |
| Repeating error BP52 | 7 | 0.44% |
| Safety chain open | 6 | 0.38% |

### Top messages: Penmanshiel_SCADA_2016_WT01-10_3107.zip::Status_Penmanshiel…

| message | count | share |
| --- | --- | --- |
| Wind < start wind | 821 | 46.07% |
| System OK | 597 | 33.50% |
| P output externally reduced | 68 | 3.82% |
| Battery charge cycle axis 1 error | 54 | 3.03% |
| Externally stopped | 52 | 2.92% |
| Manual stop - on site | 30 | 1.68% |
| Comm. failure FPM | 26 | 1.46% |
| Absence of wind during run-up | 24 | 1.35% |
| Battery test | 24 | 1.35% |
| Battery charge cycle axis 2 error | 12 | 0.67% |
| Battery charge cycle axis 3 error | 12 | 0.67% |
| Manual yaw | 12 | 0.67% |
| Frequency converter not ready | 9 | 0.51% |
| Cable autounwind | 8 | 0.45% |
| Repeating error BP52 | 7 | 0.39% |
| Grid loss | 6 | 0.34% |
| Gearbox warm-up stage | 5 | 0.28% |
| High frequency - P reduction | 5 | 0.28% |
| Park master stop | 5 | 0.28% |
| Timeout brake closed | 5 | 0.28% |

### Top messages: Penmanshiel_SCADA_2016_WT01-10_3107.zip::Status_Penmanshiel…

| message | count | share |
| --- | --- | --- |
| Wind < start wind | 383 | 34.57% |
| System OK | 376 | 33.94% |
| Overfrequency | 96 | 8.66% |
| P output externally reduced | 51 | 4.60% |
| Externally stopped | 47 | 4.24% |
| Manual stop - on site | 24 | 2.17% |
| Battery test | 19 | 1.71% |
| Absence of wind during run-up | 15 | 1.35% |
| Manual yaw | 15 | 1.35% |
| Battery charge cycle axis 1 error | 10 | 0.90% |
| Battery charge cycle axis 2 error | 10 | 0.90% |
| Battery charge cycle axis 3 error | 10 | 0.90% |
| Comm. failure FPM | 10 | 0.90% |
| Frequency converter not ready | 8 | 0.72% |
| Brake accumulator defect | 6 | 0.54% |
| High frequency - P reduction | 6 | 0.54% |
| Park master stop | 6 | 0.54% |
| Timeout brake closed | 6 | 0.54% |
| Cable panel breaker open | 5 | 0.45% |
| Repeating error BP52 | 5 | 0.45% |

### Top messages: Penmanshiel_SCADA_2016_WT01-10_3107.zip::Status_Penmanshiel…

| message | count | share |
| --- | --- | --- |
| Wind < start wind | 486 | 38.73% |
| System OK | 459 | 36.57% |
| Overfrequency | 63 | 5.02% |
| P output externally reduced | 54 | 4.30% |
| Externally stopped | 47 | 3.75% |
| Battery test | 19 | 1.51% |
| Manual yaw | 16 | 1.27% |
| Frequency converter not ready | 15 | 1.20% |
| Manual stop - on site | 15 | 1.20% |
| Absence of wind during run-up | 10 | 0.80% |
| Brake accumulator defect | 10 | 0.80% |
| Comm. failure FPM | 10 | 0.80% |
| Repeating error BP52 | 9 | 0.72% |
| Battery charge cycle axis 1 error | 7 | 0.56% |
| Battery charge cycle axis 2 error | 7 | 0.56% |
| Battery charge cycle axis 3 error | 7 | 0.56% |
| Gearbox warm-up stage | 6 | 0.48% |
| Cable autounwind | 5 | 0.40% |
| Park master stop | 5 | 0.40% |
| Timeout brake closed | 5 | 0.40% |

### Top messages: Penmanshiel_SCADA_2016_WT01-10_3107.zip::Status_Penmanshiel…

| message | count | share |
| --- | --- | --- |
| System OK | 513 | 41.04% |
| Wind < start wind | 468 | 37.44% |
| P output externally reduced | 63 | 5.04% |
| Externally stopped | 47 | 3.76% |
| Manual stop - on site | 23 | 1.84% |
| Manual yaw | 18 | 1.44% |
| Battery test | 17 | 1.36% |
| Comm. failure FPM | 15 | 1.20% |
| Repeating error BP52 | 12 | 0.96% |
| Absence of wind during run-up | 11 | 0.88% |
| Frequency converter not ready | 11 | 0.88% |
| Missing gear oil (high rpm) | 9 | 0.72% |
| Brake accumulator defect | 8 | 0.64% |
| Overfrequency | 8 | 0.64% |
| Gearbox warm-up stage | 7 | 0.56% |
| Battery charge cycle axis 1 error | 4 | 0.32% |
| Battery charge cycle axis 2 error | 4 | 0.32% |
| Battery charge cycle axis 3 error | 4 | 0.32% |
| Cable autounwind | 4 | 0.32% |
| Grid loss | 4 | 0.32% |

### Top messages: Penmanshiel_SCADA_2016_WT11-15_3107.zip::Status_Penmanshiel…

| message | count | share |
| --- | --- | --- |
| Wind < start wind | 418 | 43.68% |
| System OK | 302 | 31.56% |
| P output externally reduced | 53 | 5.54% |
| Externally stopped | 45 | 4.70% |
| Overfrequency | 24 | 2.51% |
| Battery test | 17 | 1.78% |
| Manual yaw | 16 | 1.67% |
| Comm. failure FPM | 13 | 1.36% |
| Manual stop - on site | 12 | 1.25% |
| Brake accumulator defect | 8 | 0.84% |
| Repeating error BP52 | 7 | 0.73% |
| Lightning protection defect | 6 | 0.63% |
| Timeout brake closed | 6 | 0.63% |
| Cable autounwind | 5 | 0.52% |
| Max. wind speed | 5 | 0.52% |
| Park master stop | 5 | 0.52% |
| Absence of wind during run-up | 4 | 0.42% |
| Frequency converter not ready | 4 | 0.42% |
| Overload generator fan 3 | 4 | 0.42% |
| Overload generator fan 2 | 3 | 0.31% |

### Top messages: Penmanshiel_SCADA_2016_WT11-15_3107.zip::Status_Penmanshiel…

| message | count | share |
| --- | --- | --- |
| System OK | 314 | 31.24% |
| Wind < start wind | 297 | 29.55% |
| Overfrequency | 165 | 16.42% |
| P output externally reduced | 56 | 5.57% |
| Externally stopped | 45 | 4.48% |
| Manual stop - on site | 23 | 2.29% |
| Max. wind speed | 17 | 1.69% |
| Battery test | 14 | 1.39% |
| Manual yaw | 13 | 1.29% |
| Comm. failure FPM | 10 | 1.00% |
| Battery charge cycle axis 1 error | 6 | 0.60% |
| Battery charge cycle axis 2 error | 6 | 0.60% |
| Battery charge cycle axis 3 error | 6 | 0.60% |
| Repeating error BP52 | 6 | 0.60% |
| Timeout brake closed | 6 | 0.60% |
| Error brake resistor CHP | 5 | 0.50% |
| Brake accumulator defect | 4 | 0.40% |
| Cable autounwind | 4 | 0.40% |
| Manual stop - remote | 4 | 0.40% |
| Pitch batteries charging cycle | 4 | 0.40% |

### Top messages: Penmanshiel_SCADA_2016_WT11-15_3107.zip::Status_Penmanshiel…

| message | count | share |
| --- | --- | --- |
| System OK | 337 | 38.38% |
| Wind < start wind | 326 | 37.13% |
| P output externally reduced | 50 | 5.69% |
| Externally stopped | 42 | 4.78% |
| Battery test | 16 | 1.82% |
| Max. wind speed | 15 | 1.71% |
| Overfrequency | 13 | 1.48% |
| Comm. failure FPM | 12 | 1.37% |
| Manual stop - on site | 11 | 1.25% |
| Manual yaw | 9 | 1.03% |
| Frequency converter not ready | 7 | 0.80% |
| Brake accumulator defect | 6 | 0.68% |
| Cable autounwind | 6 | 0.68% |
| Timeout brake closed | 6 | 0.68% |
| Repeating error BP52 | 5 | 0.57% |
| Grid loss | 4 | 0.46% |
| Park master stop | 4 | 0.46% |
| Absence of wind during run-up | 3 | 0.34% |
| High frequency - P reduction | 3 | 0.34% |
| Tower oscillation Y level 1 | 3 | 0.34% |

## Header samples (first lines, one member per kind)

**Penmanshiel_SCADA_2016_WT01-10_3107.zip::Turbine_Data_Penmanshiel_01_2016-06-06_-_2017-01-01_1042.csv**

```text
# This file was exported by Greenbyte at 2022-02-01 13:06:11. Please see https://www.greenbyte.com for more information about Greenbyte.
#
# Turbine: Penmanshiel 01
# Turbine type: Senvion MM82
# Time zone: UTC
# Time interval: 2016-01-01 00:00:00 - 2017-01-01 00:00:00 (366 days)
#
# Data that is missing or is erroneous has been marked with the value "NaN"
#
# Date and time,Wind speed (m/s),"Wind speed, Standard deviation (m/s)","Wind speed, Minimum (m/s)","Wind speed, Maximum (m/s)",Long Term Wind (m/s),Wind speed Sensor 1 (m/s),"Wind speed Sensor 1, Sta
2016-06-06 18:10:00,0,0,0,0,5.8,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,NaN,0,NaN,0,3.9521666924158727,3.9521666924158727,NaN,0,3.9521666924158727,NaN,0,78.34908813138546,3.9521666924158727,3.9521
2016-06-06 18:20:00,3.55999994277954,0.839999973773956,1.27999997138977,5.40999984741211,5.8,3.64000010490417,0.819999992847443,1.21000003814697,5.57000017166138,3.48000001907349,0.939999997615814,0.3
2016-06-06 18:30:00,3,0.540000021457672,1.41999995708466,4.78000020980835,5.8,3.04999995231628,0.550000011920929,1.46000003814697,4.8899998664856,2.94000005722046,0.569999992847443,0.660000026226044,4
2016-06-06 18:40:00,2.54999995231628,0.430000007152557,1.11000001430511,3.52999997138977,5.8,2.5699999332428,0.419999986886978,1.27999997138977,3.61999988555908,2.51999998092651,0.479999989271164,0.56
2016-06-06 18:50:00,2.78999996185303,0.490000009536743,1.55999994277954,3.69000005722046,5.8,2.76999998092651,0.479999989271164,1.60000002384186,3.72000002861023,2.80999994277954,0.519999980926514,1.3
2016-06-06 19:00:00,3.22000002861023,0.610000014305115,1.25,4.3899998664856,5.8,3.20000004768372,0.610000014305115,1.25,4.32999992370605,3.25,0.639999985694885,1.14999997615814,4.53000020980835,3.1815
2016-06-06 19:10:00,3.40000009536743,0.589999973773956,1.10000002384186,4.59000015258789,5.8,3.38000011444092,0.569999992847443,1.33000004291534,4.51999998092651,3.42000007629395,0.649999976158142,0.6
2016-06-06 19:20:00,2.66000008583069,0.540000021457672,0.759999990463257,3.85999989509583,5.8,2.64000010490417,0.519999980926514,0.759999990463257,3.76999998092651,2.67000007629395,0.579999983310699,0
2016-06-06 19:30:00,2.72000002861023,0.550000011920929,0.930000007152557,3.75999999046326,5.8,2.69000005722046,0.569999992847443,0.819999992847443,3.73000001907349,2.75,0.560000002384186,0.58999997377
2016-06-06 19:40:00,2.83999991416931,0.469999998807907,0.860000014305115,3.98000001907349,5.8,2.79999995231628,0.479999989271164,0.870000004768372,3.95000004768372,2.89000010490417,0.479999989271164,0
2016-06-06 19:50:00,3.30999994277954,0.28999999165535,2.17000007629395,4.07999992370605,5.8,3.25999999046326,0.280000001192093,2.46000003814697,3.99000000953674,3.35999989509583,0.300000011920929,1.87
2016-06-06 20:00:00,2.85999989509583,0.349999994039536,1.79999995231628,3.65000009536743,5.8,2.78999996185303,0.340000003576279,1.85000002384186,3.57999992370605,2.92000007629395,0.379999995231628,1.5
2016-06-06 20:10:00,3.34999990463257,0.300000011920929,2.28999996185303,4.01000022888184,5.8,3.30999994277954,0.310000002384186,2.30999994277954,4.01000022888184,3.39000010490417,0.319999992847443,2.0
2016-06-06 20:20:00,3.20000004768372,0.449999988079071,1.99000000953674,4.15000009536743,5.8,3.1800000667572,0.419999986886978,2.13000011444092,4.19000005722046,3.23000001907349,0.490000009536743,1.69
2016-06-06 20:30:00,3.51999998092651,0.349999994039536,2.73000001907349,4.05999994277954,5.8,3.48000001907349,0.379999995231628,2.74000000953674,4.09999990463257,3.55999994277954,0.319999992847443,2.6
2016-06-06 20:40:00,2.90000009536743,0.409999996423721,2.08999991416931,3.82999992370605,5.8,2.86999988555908,0.400000005960464,2.1800000667572,3.82999992370605,2.9300000667572,0.439999997615814,1.809
2016-06-06 20:50:00,3.04999995231628,0.319999992847443,1.45000004768372,3.41000008583069,5.8,3.02999997138977,0.310000002384186,1.75,3.44000005722046,3.0699999332428,0.340000003576279,1.00999999046326
2016-06-06 21:00:00,2.92000007629395,0.259999990463257,2.27999997138977,3.50999999046326,5.8,2.85999989509583,0.270000010728836,2.3199999332428,3.53999996185303,2.97000002861023,0.270000010728836,2.14
2016-06-06 21:10:00,2.75999999046326,0.180000007152557,1.95000004768372,3.21000003814697,5.8,2.74000000953674,0.170000001788139,2.11999988555908,3.23000001907349,2.77999997138977,0.219999998807907,1.5
2016-06-06 21:20:00,2.75,0.140000000596046,2.40000009536743,3.05999994277954,5.8,2.75,0.170000001788139,2.42000007629395,3.10999989509583,2.75999999046326,0.129999995231628,2.25999999046326,3.03999996
```

**Penmanshiel_SCADA_2016_WT01-10_3107.zip::Status_Penmanshiel_01_2016-06-06_-_2017-01-01_1042.csv**

```text
# This file was exported by Greenbyte at 2022-02-01 13:16:19. Please see https://www.greenbyte.com for more information about Greenbyte.
#
# Turbine: Penmanshiel 01
# Turbine type: Senvion MM82 (Senvion MM82 kW)
# Time zone: UTC
# Time interval: 2016-01-01 00:00:00 - 2017-01-01 00:00:00 (366 days)
#
# Penmanshiel 01 Sum production: 2614804 kWh
#
Timestamp start,Timestamp end,Duration,Status,Code,Message,Comment,Service contract category,IEC category
2016-06-06 17:08:40,2016-06-10 11:28:00,90:19:20,Stop,3500,Grid loss,,External stop (grid) (4),Out of Electrical Specification
2016-06-06 17:08:41,2016-06-06 18:14:07,01:05:26,Warning,3875,Overload transf. fan inlet air,,Warnings (27),
2016-06-06 17:08:41,2016-06-06 18:14:39,01:05:58,Warning,1825,Overload gear bypass filter,,Warnings (27),
2016-06-06 17:08:41,2016-06-06 18:14:07,01:05:26,Warning,3875,Overload transf. fan inlet air,,Warnings (27),
2016-06-06 17:08:41,2016-06-06 18:14:39,01:05:58,Warning,1825,Overload gear bypass filter,,Warnings (27),
2016-06-06 17:08:52,2016-06-06 18:15:02,01:06:10,Warning,8402,No assignment to a PMU,,Warnings (27),
2016-06-06 17:08:52,2016-06-06 18:15:02,01:06:10,Warning,8402,No assignment to a PMU,,Warnings (27),
2016-06-08 01:34:01,2016-06-11 00:56:54,71:22:53,Warning,7324,Check time synchronization,,Warnings (27),
2016-06-08 01:34:01,2016-06-11 00:56:54,71:22:53,Warning,7324,Check time synchronization,,Warnings (27),
2016-06-10 11:28:00,2016-06-10 11:30:53,00:02:53,Informational,0,System OK,,System OK (32),Full Performance
2016-06-10 11:28:00,2016-06-10 11:30:53,00:02:53,Informational,0,System OK,,System OK (32),Full Performance
2016-06-10 11:30:53,2016-06-10 11:33:05,00:02:12,Warning,5720,Brake accumulator defect,,Warnings (27),
2016-06-10 11:30:53,2016-06-10 11:57:04,00:26:11,Stop,2100,Feedback brake 1,,Mechanical error (23),Forced outage
2016-06-10 11:30:53,2016-06-10 11:33:05,00:02:12,Warning,5720,Brake accumulator defect,,Warnings (27),
2016-06-10 11:33:05,2016-06-10 11:33:07,00:00:02,Informational,0,System OK,,System OK (32),Full Performance
2016-06-10 11:33:05,2016-06-10 11:33:07,00:00:02,Informational,0,System OK,,System OK (32),Full Performance
2016-06-10 11:33:13,2016-06-10 12:46:40,01:13:27,Informational,6410,Manual yaw,,Manual stop (service)  (9),Full Performance
2016-06-10 11:33:13,2016-06-10 12:46:40,01:13:27,Informational,6410,Manual yaw,,Manual stop (service)  (9),Full Performance
2016-06-10 11:34:58,2016-06-10 11:37:56,00:02:58,Warning,5100,Service obstacle light,,Warnings (27),
2016-06-10 11:34:58,2016-06-10 11:37:56,00:02:58,Warning,5100,Service obstacle light,,Warnings (27),
```

## Member listing (112 of 112)

| archive | member | kind | uncompressed (MB) | compressed (MB) |
| --- | --- | --- | --- | --- |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip | Turbine_Data_Penmanshiel_01_2016-06-06_-_2017-01-01_1042.csv | scada_10min | 82.36 | 16.1 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip | Status_Penmanshiel_01_2016-06-06_-_2017-01-01_1042.csv | status_events | 0.356 | 0.024 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip | Turbine_Data_Penmanshiel_02_2016-06-03_-_2017-01-01_1043.csv | scada_10min | 83.8 | 16.19 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip | Status_Penmanshiel_02_2016-06-03_-_2017-01-01_1043.csv | status_events | 0.219 | 0.023 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip | Turbine_Data_Penmanshiel_04_2016-06-13_-_2017-01-01_1044.csv | scada_10min | 80.6 | 15.84 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip | Status_Penmanshiel_04_2016-06-13_-_2017-01-01_1044.csv | status_events | 0.188 | 0.02 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip | Turbine_Data_Penmanshiel_05_2016-06-15_-_2017-01-01_1045.csv | scada_10min | 81.39 | 16.08 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip | Status_Penmanshiel_05_2016-06-15_-_2017-01-01_1045.csv | status_events | 0.202 | 0.021 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip | Turbine_Data_Penmanshiel_06_2016-06-02_-_2017-01-01_1046.csv | scada_10min | 79.86 | 14.77 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip | Status_Penmanshiel_06_2016-06-02_-_2017-01-01_1046.csv | status_events | 0.213 | 0.024 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip | Turbine_Data_Penmanshiel_07_2016-06-02_-_2017-01-01_1047.csv | scada_10min | 84.59 | 16.48 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip | Status_Penmanshiel_07_2016-06-02_-_2017-01-01_1047.csv | status_events | 0.246 | 0.025 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip | Turbine_Data_Penmanshiel_08_2016-07-27_-_2017-01-01_1048.csv | scada_10min | 58.59 | 11.2 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip | Status_Penmanshiel_08_2016-07-27_-_2017-01-01_1048.csv | status_events | 0.15 | 0.017 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip | Turbine_Data_Penmanshiel_09_2016-06-24_-_2017-01-01_1049.csv | scada_10min | 63.93 | 11.23 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip | Status_Penmanshiel_09_2016-06-24_-_2017-01-01_1049.csv | status_events | 0.171 | 0.018 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip | Turbine_Data_Penmanshiel_10_2016-06-27_-_2017-01-01_1050.csv | scada_10min | 62.63 | 10.85 |
| Penmanshiel_SCADA_2016_WT01-10_3107.zip | Status_Penmanshiel_10_2016-06-27_-_2017-01-01_1050.csv | status_events | 0.168 | 0.018 |
| Penmanshiel_SCADA_2016_WT11-15_3107.zip | Turbine_Data_Penmanshiel_11_2016-07-19_-_2017-01-01_1051.csv | scada_10min | 60.01 | 11.24 |
| Penmanshiel_SCADA_2016_WT11-15_3107.zip | Status_Penmanshiel_11_2016-07-19_-_2017-01-01_1051.csv | status_events | 0.135 | 0.015 |
| Penmanshiel_SCADA_2016_WT11-15_3107.zip | Turbine_Data_Penmanshiel_12_2016-07-02_-_2017-01-01_1052.csv | scada_10min | 63.82 | 11.45 |
| Penmanshiel_SCADA_2016_WT11-15_3107.zip | Status_Penmanshiel_12_2016-07-02_-_2017-01-01_1052.csv | status_events | 0.135 | 0.016 |
| Penmanshiel_SCADA_2016_WT11-15_3107.zip | Turbine_Data_Penmanshiel_13_2016-06-30_-_2017-01-01_1053.csv | scada_10min | 63.24 | 11.36 |
| Penmanshiel_SCADA_2016_WT11-15_3107.zip | Status_Penmanshiel_13_2016-06-30_-_2017-01-01_1053.csv | status_events | 0.118 | 0.013 |
| Penmanshiel_SCADA_2016_WT11-15_3107.zip | Turbine_Data_Penmanshiel_14_2016-07-09_-_2017-01-01_1054.csv | scada_10min | 60.44 | 10.76 |
| Penmanshiel_SCADA_2016_WT11-15_3107.zip | Status_Penmanshiel_14_2016-07-09_-_2017-01-01_1054.csv | status_events | 0.134 | 0.015 |
| Penmanshiel_SCADA_2016_WT11-15_3107.zip | Turbine_Data_Penmanshiel_15_2016-07-14_-_2017-01-01_1056.csv | scada_10min | 60.49 | 11.04 |
| Penmanshiel_SCADA_2016_WT11-15_3107.zip | Status_Penmanshiel_15_2016-07-14_-_2017-01-01_1056.csv | status_events | 0.139 | 0.016 |
| Penmanshiel_SCADA_2017_WT01-10_3114.zip | Turbine_Data_Penmanshiel_01_2017-01-01_-_2018-01-01_1042.csv | scada_10min | 149.9 | 30.51 |
| Penmanshiel_SCADA_2017_WT01-10_3114.zip | Status_Penmanshiel_01_2017-01-01_-_2018-01-01_1042.csv | status_events | 0.532 | 0.033 |
| Penmanshiel_SCADA_2017_WT01-10_3114.zip | Turbine_Data_Penmanshiel_02_2017-01-01_-_2018-01-01_1043.csv | scada_10min | 150 | 30.53 |
| Penmanshiel_SCADA_2017_WT01-10_3114.zip | Status_Penmanshiel_02_2017-01-01_-_2018-01-01_1043.csv | status_events | 0.368 | 0.034 |
| Penmanshiel_SCADA_2017_WT01-10_3114.zip | Turbine_Data_Penmanshiel_04_2017-01-01_-_2018-01-01_1044.csv | scada_10min | 149.1 | 30.5 |
| Penmanshiel_SCADA_2017_WT01-10_3114.zip | Status_Penmanshiel_04_2017-01-01_-_2018-01-01_1044.csv | status_events | 0.278 | 0.026 |
| Penmanshiel_SCADA_2017_WT01-10_3114.zip | Turbine_Data_Penmanshiel_05_2017-01-01_-_2018-01-01_1045.csv | scada_10min | 150.5 | 30.63 |
| Penmanshiel_SCADA_2017_WT01-10_3114.zip | Status_Penmanshiel_05_2017-01-01_-_2018-01-01_1045.csv | status_events | 0.381 | 0.035 |
| Penmanshiel_SCADA_2017_WT01-10_3114.zip | Turbine_Data_Penmanshiel_06_2017-01-01_-_2018-01-01_1046.csv | scada_10min | 147.9 | 30.34 |
| Penmanshiel_SCADA_2017_WT01-10_3114.zip | Status_Penmanshiel_06_2017-01-01_-_2018-01-01_1046.csv | status_events | 0.345 | 0.033 |
| Penmanshiel_SCADA_2017_WT01-10_3114.zip | Turbine_Data_Penmanshiel_07_2017-01-01_-_2018-01-01_1047.csv | scada_10min | 148.1 | 30.14 |
| Penmanshiel_SCADA_2017_WT01-10_3114.zip | Status_Penmanshiel_07_2017-01-01_-_2018-01-01_1047.csv | status_events | 0.407 | 0.037 |
| Penmanshiel_SCADA_2017_WT01-10_3114.zip | Turbine_Data_Penmanshiel_08_2017-01-01_-_2018-01-01_1048.csv | scada_10min | 147.8 | 30.37 |
| Penmanshiel_SCADA_2017_WT01-10_3114.zip | Status_Penmanshiel_08_2017-01-01_-_2018-01-01_1048.csv | status_events | 0.324 | 0.03 |
| Penmanshiel_SCADA_2017_WT01-10_3114.zip | Turbine_Data_Penmanshiel_09_2017-01-01_-_2018-01-01_1049.csv | scada_10min | 147.3 | 30.09 |
| Penmanshiel_SCADA_2017_WT01-10_3114.zip | Status_Penmanshiel_09_2017-01-01_-_2018-01-01_1049.csv | status_events | 0.42 | 0.038 |
| Penmanshiel_SCADA_2017_WT01-10_3114.zip | Turbine_Data_Penmanshiel_10_2017-01-01_-_2018-01-01_1050.csv | scada_10min | 147.4 | 30.12 |
| Penmanshiel_SCADA_2017_WT01-10_3114.zip | Status_Penmanshiel_10_2017-01-01_-_2018-01-01_1050.csv | status_events | 0.422 | 0.038 |
| Penmanshiel_SCADA_2017_WT11-15_3115.zip | Turbine_Data_Penmanshiel_11_2017-01-01_-_2018-01-01_1051.csv | scada_10min | 149.1 | 30.44 |
| Penmanshiel_SCADA_2017_WT11-15_3115.zip | Status_Penmanshiel_11_2017-01-01_-_2018-01-01_1051.csv | status_events | 0.3 | 0.028 |
| Penmanshiel_SCADA_2017_WT11-15_3115.zip | Turbine_Data_Penmanshiel_12_2017-01-01_-_2018-01-01_1052.csv | scada_10min | 149.8 | 30.64 |
| Penmanshiel_SCADA_2017_WT11-15_3115.zip | Status_Penmanshiel_12_2017-01-01_-_2018-01-01_1052.csv | status_events | 0.258 | 0.024 |
| Penmanshiel_SCADA_2017_WT11-15_3115.zip | Turbine_Data_Penmanshiel_13_2017-01-01_-_2018-01-01_1053.csv | scada_10min | 149 | 30.71 |
| Penmanshiel_SCADA_2017_WT11-15_3115.zip | Status_Penmanshiel_13_2017-01-01_-_2018-01-01_1053.csv | status_events | 0.213 | 0.021 |
| Penmanshiel_SCADA_2017_WT11-15_3115.zip | Turbine_Data_Penmanshiel_14_2017-01-01_-_2018-01-01_1054.csv | scada_10min | 148.2 | 30.48 |
| Penmanshiel_SCADA_2017_WT11-15_3115.zip | Status_Penmanshiel_14_2017-01-01_-_2018-01-01_1054.csv | status_events | 0.302 | 0.028 |
| Penmanshiel_SCADA_2017_WT11-15_3115.zip | Turbine_Data_Penmanshiel_15_2017-01-01_-_2018-01-01_1056.csv | scada_10min | 148.2 | 30.5 |
| Penmanshiel_SCADA_2017_WT11-15_3115.zip | Status_Penmanshiel_15_2017-01-01_-_2018-01-01_1056.csv | status_events | 0.283 | 0.027 |
| Penmanshiel_SCADA_2018_WT01-10_3113.zip | Turbine_Data_Penmanshiel_01_2018-01-01_-_2019-01-01_1042.csv | scada_10min | 146.2 | 39.52 |
| Penmanshiel_SCADA_2018_WT01-10_3113.zip | Status_Penmanshiel_01_2018-01-01_-_2019-01-01_1042.csv | status_events | 0.847 | 0.061 |
| Penmanshiel_SCADA_2018_WT01-10_3113.zip | Turbine_Data_Penmanshiel_02_2018-01-01_-_2019-01-01_1043.csv | scada_10min | 146.6 | 40.68 |
| Penmanshiel_SCADA_2018_WT01-10_3113.zip | Status_Penmanshiel_02_2018-01-01_-_2019-01-01_1043.csv | status_events | 0.961 | 0.074 |
| Penmanshiel_SCADA_2018_WT01-10_3113.zip | Turbine_Data_Penmanshiel_04_2018-01-01_-_2019-01-01_1044.csv | scada_10min | 147.1 | 40.69 |
| Penmanshiel_SCADA_2018_WT01-10_3113.zip | Status_Penmanshiel_04_2018-01-01_-_2019-01-01_1044.csv | status_events | 0.813 | 0.063 |
| Penmanshiel_SCADA_2018_WT01-10_3113.zip | Turbine_Data_Penmanshiel_05_2018-01-01_-_2019-01-01_1045.csv | scada_10min | 148 | 41.28 |
| Penmanshiel_SCADA_2018_WT01-10_3113.zip | Status_Penmanshiel_05_2018-01-01_-_2019-01-01_1045.csv | status_events | 1.165 | 0.087 |
| Penmanshiel_SCADA_2018_WT01-10_3113.zip | Turbine_Data_Penmanshiel_06_2018-01-01_-_2019-01-01_1046.csv | scada_10min | 146.6 | 40.42 |
| Penmanshiel_SCADA_2018_WT01-10_3113.zip | Status_Penmanshiel_06_2018-01-01_-_2019-01-01_1046.csv | status_events | 0.895 | 0.069 |
| Penmanshiel_SCADA_2018_WT01-10_3113.zip | Turbine_Data_Penmanshiel_07_2018-01-01_-_2019-01-01_1047.csv | scada_10min | 146.6 | 40.67 |
| Penmanshiel_SCADA_2018_WT01-10_3113.zip | Status_Penmanshiel_07_2018-01-01_-_2019-01-01_1047.csv | status_events | 1.059 | 0.08 |
| Penmanshiel_SCADA_2018_WT01-10_3113.zip | Turbine_Data_Penmanshiel_08_2018-01-01_-_2019-01-01_1048.csv | scada_10min | 146.9 | 40.83 |
| Penmanshiel_SCADA_2018_WT01-10_3113.zip | Status_Penmanshiel_08_2018-01-01_-_2019-01-01_1048.csv | status_events | 0.82 | 0.063 |
| Penmanshiel_SCADA_2018_WT01-10_3113.zip | Turbine_Data_Penmanshiel_09_2018-01-01_-_2019-01-01_1049.csv | scada_10min | 146.1 | 40.33 |
| Penmanshiel_SCADA_2018_WT01-10_3113.zip | Status_Penmanshiel_09_2018-01-01_-_2019-01-01_1049.csv | status_events | 0.967 | 0.074 |
| Penmanshiel_SCADA_2018_WT01-10_3113.zip | Turbine_Data_Penmanshiel_10_2018-01-01_-_2019-01-01_1050.csv | scada_10min | 145.4 | 39.95 |
| Penmanshiel_SCADA_2018_WT01-10_3113.zip | Status_Penmanshiel_10_2018-01-01_-_2019-01-01_1050.csv | status_events | 1.02 | 0.078 |
| Penmanshiel_SCADA_2018_WT11-15_3116.zip | Turbine_Data_Penmanshiel_11_2018-01-01_-_2019-01-01_1051.csv | scada_10min | 147.2 | 40.7 |
| Penmanshiel_SCADA_2018_WT11-15_3116.zip | Status_Penmanshiel_11_2018-01-01_-_2019-01-01_1051.csv | status_events | 0.808 | 0.063 |
| Penmanshiel_SCADA_2018_WT11-15_3116.zip | Turbine_Data_Penmanshiel_12_2018-01-01_-_2019-01-01_1052.csv | scada_10min | 147.6 | 40.71 |
| Penmanshiel_SCADA_2018_WT11-15_3116.zip | Status_Penmanshiel_12_2018-01-01_-_2019-01-01_1052.csv | status_events | 0.697 | 0.055 |
| Penmanshiel_SCADA_2018_WT11-15_3116.zip | Turbine_Data_Penmanshiel_13_2018-01-01_-_2019-01-01_1053.csv | scada_10min | 147.9 | 41.19 |
| Penmanshiel_SCADA_2018_WT11-15_3116.zip | Status_Penmanshiel_13_2018-01-01_-_2019-01-01_1053.csv | status_events | 0.774 | 0.06 |
| Penmanshiel_SCADA_2018_WT11-15_3116.zip | Turbine_Data_Penmanshiel_14_2018-01-01_-_2019-01-01_1054.csv | scada_10min | 147 | 40.86 |
| Penmanshiel_SCADA_2018_WT11-15_3116.zip | Status_Penmanshiel_14_2018-01-01_-_2019-01-01_1054.csv | status_events | 0.815 | 0.064 |
| Penmanshiel_SCADA_2018_WT11-15_3116.zip | Turbine_Data_Penmanshiel_15_2018-01-01_-_2019-01-01_1056.csv | scada_10min | 147.4 | 41.05 |
| Penmanshiel_SCADA_2018_WT11-15_3116.zip | Status_Penmanshiel_15_2018-01-01_-_2019-01-01_1056.csv | status_events | 0.754 | 0.059 |
| Penmanshiel_SCADA_2019_WT01-10_3112.zip | Turbine_Data_Penmanshiel_01_2019-01-01_-_2020-01-01_1042.csv | scada_10min | 151.9 | 52.59 |
| Penmanshiel_SCADA_2019_WT01-10_3112.zip | Status_Penmanshiel_01_2019-01-01_-_2020-01-01_1042.csv | status_events | 0.907 | 0.069 |
| Penmanshiel_SCADA_2019_WT01-10_3112.zip | Turbine_Data_Penmanshiel_02_2019-01-01_-_2020-01-01_1043.csv | scada_10min | 150.8 | 52.9 |
| Penmanshiel_SCADA_2019_WT01-10_3112.zip | Status_Penmanshiel_02_2019-01-01_-_2020-01-01_1043.csv | status_events | 1.093 | 0.082 |
| Penmanshiel_SCADA_2019_WT01-10_3112.zip | Turbine_Data_Penmanshiel_04_2019-01-01_-_2020-01-01_1044.csv | scada_10min | 151.6 | 53.05 |
| Penmanshiel_SCADA_2019_WT01-10_3112.zip | Status_Penmanshiel_04_2019-01-01_-_2020-01-01_1044.csv | status_events | 0.977 | 0.073 |
| Penmanshiel_SCADA_2019_WT01-10_3112.zip | Turbine_Data_Penmanshiel_05_2019-01-01_-_2020-01-01_1045.csv | scada_10min | 150.6 | 52.79 |
| Penmanshiel_SCADA_2019_WT01-10_3112.zip | Status_Penmanshiel_05_2019-01-01_-_2020-01-01_1045.csv | status_events | 1.187 | 0.088 |
| Penmanshiel_SCADA_2019_WT01-10_3112.zip | Turbine_Data_Penmanshiel_06_2019-01-01_-_2020-01-01_1046.csv | scada_10min | 151.8 | 52.62 |
| Penmanshiel_SCADA_2019_WT01-10_3112.zip | Status_Penmanshiel_06_2019-01-01_-_2020-01-01_1046.csv | status_events | 1.11 | 0.083 |
| Penmanshiel_SCADA_2019_WT01-10_3112.zip | Turbine_Data_Penmanshiel_07_2019-01-01_-_2020-01-01_1047.csv | scada_10min | 147.8 | 50.84 |
| Penmanshiel_SCADA_2019_WT01-10_3112.zip | Status_Penmanshiel_07_2019-01-01_-_2020-01-01_1047.csv | status_events | 1.165 | 0.087 |
| Penmanshiel_SCADA_2019_WT01-10_3112.zip | Turbine_Data_Penmanshiel_08_2019-01-01_-_2020-01-01_1048.csv | scada_10min | 151.6 | 52.85 |
| Penmanshiel_SCADA_2019_WT01-10_3112.zip | Status_Penmanshiel_08_2019-01-01_-_2020-01-01_1048.csv | status_events | 0.853 | 0.065 |
| Penmanshiel_SCADA_2019_WT01-10_3112.zip | Turbine_Data_Penmanshiel_09_2019-01-01_-_2020-01-01_1049.csv | scada_10min | 150.5 | 52.57 |
| Penmanshiel_SCADA_2019_WT01-10_3112.zip | Status_Penmanshiel_09_2019-01-01_-_2020-01-01_1049.csv | status_events | 1.096 | 0.081 |
| Penmanshiel_SCADA_2019_WT01-10_3112.zip | Turbine_Data_Penmanshiel_10_2019-01-01_-_2020-01-01_1050.csv | scada_10min | 150.9 | 52.58 |
| Penmanshiel_SCADA_2019_WT01-10_3112.zip | Status_Penmanshiel_10_2019-01-01_-_2020-01-01_1050.csv | status_events | 1.141 | 0.084 |
| Penmanshiel_SCADA_2019_WT11-15_3117.zip | Turbine_Data_Penmanshiel_11_2019-01-01_-_2020-01-01_1051.csv | scada_10min | 151.2 | 52.79 |
| Penmanshiel_SCADA_2019_WT11-15_3117.zip | Status_Penmanshiel_11_2019-01-01_-_2020-01-01_1051.csv | status_events | 0.859 | 0.065 |
| Penmanshiel_SCADA_2019_WT11-15_3117.zip | Turbine_Data_Penmanshiel_12_2019-01-01_-_2020-01-01_1052.csv | scada_10min | 151.2 | 53.08 |
| Penmanshiel_SCADA_2019_WT11-15_3117.zip | Status_Penmanshiel_12_2019-01-01_-_2020-01-01_1052.csv | status_events | 0.738 | 0.058 |
| Penmanshiel_SCADA_2019_WT11-15_3117.zip | Turbine_Data_Penmanshiel_13_2019-01-01_-_2020-01-01_1053.csv | scada_10min | 152.4 | 53.2 |
| Penmanshiel_SCADA_2019_WT11-15_3117.zip | Status_Penmanshiel_13_2019-01-01_-_2020-01-01_1053.csv | status_events | 0.916 | 0.069 |
| Penmanshiel_SCADA_2019_WT11-15_3117.zip | Turbine_Data_Penmanshiel_14_2019-01-01_-_2020-01-01_1054.csv | scada_10min | 151.7 | 52.96 |
| Penmanshiel_SCADA_2019_WT11-15_3117.zip | Status_Penmanshiel_14_2019-01-01_-_2020-01-01_1054.csv | status_events | 0.968 | 0.073 |
| Penmanshiel_SCADA_2019_WT11-15_3117.zip | Turbine_Data_Penmanshiel_15_2019-01-01_-_2020-01-01_1056.csv | scada_10min | 151.8 | 53.01 |
| Penmanshiel_SCADA_2019_WT11-15_3117.zip | Status_Penmanshiel_15_2019-01-01_-_2020-01-01_1056.csv | status_events | 0.799 | 0.061 |
