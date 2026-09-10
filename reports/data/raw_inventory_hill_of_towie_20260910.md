# Raw inventory: hill_of_towie

| field | value |
| --- | --- |
| source | hill_of_towie |
| provider | RES on behalf of TRIG |
| licence | CC-BY-4.0 |
| zenodo record | 14,870,023 |
| concept DOI | 10.5281/zenodo.14870023 |
| staged directory | C:\Users\sharg\Desktop\github\FaultLine\data\raw\telemetry\hill_of_towie |
| files staged | 9 |
| members discovered | 319 |
| member classification | provider table names, as defined in Hill_of_Towie_tables_description.csv (tblAlarmLog: 'Log of stopping and non-stopping events/alarms'); ShutdownDuration.csv is not in that file and is classified from its header |
| event members parsed | 24 of 25 (caps: 200 members, 209.7 MB and 500,000 rows per member) |
| generated (UTC) | 2026-09-10T09:22:27+00:00 |
| git_sha | aac5d7110773da2a7337e045b61237a5001db107 |

## Free-text verdict

**VERIFIED no** - codes only: 24 event tables and 1,004,341 rows were parsed, and not one row carries a message

This is the evidence behind ADR-0001: whether the paired text in this record is open-ended language or a controlled vocabulary.

Thresholds applied: more than 500 distinct strings is open-ended text; within that, a set in which at least 50% of the distinct strings occur exactly once was written per event, otherwise it is a code book; written descriptions averaging at most 200 characters are short. The measurements are pooled over every parsed event table and listed in the next section.

## Text measurements (all parsed tables pooled)

| field | value |
| --- | --- |
| event tables parsed | 24 |
| rows | 1,004,341 |
| rows with a non-empty message | 0 (0.0%) |
| distinct messages | 0 |
| mean length (characters) | 0 |
| mean length (words) | 0 |
| distinct messages occurring exactly once | 0.0% |
| most distinct messages in one table | 0 |
| longest mean length in one table (characters) | 0 |

## Event codes (all parsed tables pooled)

| field | value |
| --- | --- |
| tables with a code column | 24 of 24 |
| rows carrying a code | 1,004,341 |
| distinct codes | 429 |

**Top 20 codes**

| code | rows | share | description in Hill_of_Towie_alarms_description.csv |
| --- | --- | --- | --- |
| 20 | 441,896 | 44.00% | Large generator Cut-in |
| 25 | 441,895 | 44.00% | Fast cut-out of generator |
| 115 | 13,560 | 1.35% | - |
| 127 | 12,071 | 1.20% | - |
| 50346 | 11,347 | 1.13% | - |
| 111 | 9,018 | 0.90% | - |
| 27 | 4,004 | 0.40% | - |
| 3130 | 2,977 | 0.30% | Pitch lubrication |
| 168 | 2,971 | 0.30% | - |
| 1005 | 2,744 | 0.27% | Availability - low wind |
| 7111 | 2,368 | 0.24% | - |
| 16 | 2,159 | 0.21% | - |
| 15 | 2,159 | 0.21% | - |
| 67 | 2,092 | 0.21% | - |
| 68 | 2,092 | 0.21% | - |
| 69 | 2,092 | 0.21% | - |
| 5122 | 1,893 | 0.19% | - |
| 50200 | 1,891 | 0.19% | - |
| 159 | 1,518 | 0.15% | - |
| 10105 | 1,508 | 0.15% | Stopped, untwisting cables |

## Provider code descriptions

| field | value |
| --- | --- |
| file | Hill_of_Towie_alarms_description.csv |
| rows in the file | 12 |
| codes described | 12 |
| distinct descriptions | 12 |
| mean description length (chars) | 23.8 |
| parsed event rows carrying a described code | 891,528 of 1,004,341 (88.8%) |
| distinct codes in the parsed tables that it describes | 8 of 429 |

**The file as published**

| Alarm Code | Description | Stopping | rows in parsed tables |
| --- | --- | --- | --- |
| 20 | Large generator Cut-in | 0 | 441,896 |
| 25 | Fast cut-out of generator | 0 | 441,895 |
| 102 | Ice detection             : | 0 | 50 |
| 1005 | Availability - low wind | 1 | 2,744 |
| 3130 | Pitch lubrication | 1 | 2,977 |
| 8000 | Windspeed too high to operate | 1 | 232 |
| 8210 | Stopped, due to icing | 1 | 0 |
| 8230 | Ice detection: Low torque | 1 | 226 |
| 8234 | Ice detection: No cut in | 1 | 0 |
| 8235 | Ice Detect: Stopped | 1 | 0 |
| 8236 | Ice Detect: Stopped, De-Ice | 1 | 0 |
| 10105 | Stopped, untwisting cables | 1 | 1,508 |

## Staged files

| file | size (MB) | members |
| --- | --- | --- |
| 2019.zip | 1,430 | 156 |
| 2023.zip | 1,512 | 156 |
| Hill_of_Towie_AeroUp_install_dates.csv | 0 | 1 |
| Hill_of_Towie_alarms_description.csv | 0 | 1 |
| Hill_of_Towie_grid_fields_description.csv | 0 | 1 |
| Hill_of_Towie_ShutdownDuration.zip | 19.8 | 1 |
| Hill_of_Towie_tables_description.csv | 0 | 1 |
| Hill_of_Towie_turbine_fields_description.csv | 0 | 1 |
| Hill_of_Towie_turbine_metadata.csv | 0 | 1 |

## Members by kind

| kind | members | uncompressed (MB) |
| --- | --- | --- |
| alarm_log | 24 | 34.2 |
| metadata | 6 | 0 |
| other | 72 | 65.5 |
| scada_10min | 216 | 1.272e+04 |
| status_events | 1 | 316.8 |

## Event tables found

| member | rows | columns | code column | message column | unique codes | unique messages | free-text share | mean chars |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2019.zip::tblAlarmLog_2019_01.csv | 24,289 | 4 | Alarmcode | - | 107 | 0 | 0.0% | 0 |
| 2019.zip::tblAlarmLog_2019_02.csv | 39,938 | 4 | Alarmcode | - | 136 | 0 | 0.0% | 0 |
| 2019.zip::tblAlarmLog_2019_03.csv | 27,831 | 4 | Alarmcode | - | 170 | 0 | 0.0% | 0 |
| 2019.zip::tblAlarmLog_2019_04.csv | 59,547 | 4 | Alarmcode | - | 176 | 0 | 0.0% | 0 |
| 2019.zip::tblAlarmLog_2019_05.csv | 84,018 | 4 | Alarmcode | - | 147 | 0 | 0.0% | 0 |
| 2019.zip::tblAlarmLog_2019_06.csv | 70,024 | 4 | Alarmcode | - | 137 | 0 | 0.0% | 0 |
| 2019.zip::tblAlarmLog_2019_07.csv | 92,563 | 4 | Alarmcode | - | 193 | 0 | 0.0% | 0 |
| 2019.zip::tblAlarmLog_2019_08.csv | 83,291 | 4 | Alarmcode | - | 162 | 0 | 0.0% | 0 |
| 2019.zip::tblAlarmLog_2019_09.csv | 58,615 | 4 | Alarmcode | - | 96 | 0 | 0.0% | 0 |
| 2019.zip::tblAlarmLog_2019_10.csv | 42,501 | 4 | Alarmcode | - | 135 | 0 | 0.0% | 0 |
| 2019.zip::tblAlarmLog_2019_11.csv | 39,138 | 4 | Alarmcode | - | 102 | 0 | 0.0% | 0 |
| 2019.zip::tblAlarmLog_2019_12.csv | 35,640 | 4 | Alarmcode | - | 77 | 0 | 0.0% | 0 |
| 2023.zip::tblAlarmLog_2023_01.csv | 15,609 | 4 | Alarmcode | - | 136 | 0 | 0.0% | 0 |
| 2023.zip::tblAlarmLog_2023_02.csv | 18,503 | 4 | Alarmcode | - | 157 | 0 | 0.0% | 0 |
| 2023.zip::tblAlarmLog_2023_03.csv | 35,269 | 4 | Alarmcode | - | 147 | 0 | 0.0% | 0 |
| 2023.zip::tblAlarmLog_2023_04.csv | 31,575 | 4 | Alarmcode | - | 167 | 0 | 0.0% | 0 |
| 2023.zip::tblAlarmLog_2023_05.csv | 41,986 | 4 | Alarmcode | - | 157 | 0 | 0.0% | 0 |
| 2023.zip::tblAlarmLog_2023_06.csv | 45,636 | 4 | Alarmcode | - | 162 | 0 | 0.0% | 0 |
| 2023.zip::tblAlarmLog_2023_07.csv | 33,318 | 4 | Alarmcode | - | 157 | 0 | 0.0% | 0 |
| 2023.zip::tblAlarmLog_2023_08.csv | 39,033 | 4 | Alarmcode | - | 169 | 0 | 0.0% | 0 |
| 2023.zip::tblAlarmLog_2023_09.csv | 28,342 | 4 | Alarmcode | - | 147 | 0 | 0.0% | 0 |
| 2023.zip::tblAlarmLog_2023_10.csv | 18,210 | 4 | Alarmcode | - | 114 | 0 | 0.0% | 0 |
| 2023.zip::tblAlarmLog_2023_11.csv | 21,274 | 4 | Alarmcode | - | 151 | 0 | 0.0% | 0 |
| 2023.zip::tblAlarmLog_2023_12.csv | 18,191 | 4 | Alarmcode | - | 115 | 0 | 0.0% | 0 |

## Event members not parsed

| member | uncompressed (MB) | reason |
| --- | --- | --- |
| Hill_of_Towie_ShutdownDuration.zip::ShutdownDuration.csv | 316.8 | 316.8 MB exceeds the parse cap of 209.7 MB |

## Header samples (first lines, one member per kind)

**2019.zip::tblAlarmLog_2019_01.csv**

```text
TimeOn,TimeOff,StationNr,Alarmcode
2019-01-01 00:04:48,,2304525,127
2019-01-01 00:05:24,,2304527,127
2019-01-01 00:08:24,,2304524,127
2019-01-03 13:59:13,,2304519,25
2019-01-03 13:59:56,,2304519,20
2019-01-03 14:01:06,,2304519,25
2019-01-03 14:02:00,,2304519,20
2019-01-03 14:02:33,,2304519,25
2019-01-03 14:03:22,,2304519,20
2019-01-03 14:04:06,,2304515,25
2019-01-03 14:04:31,,2304519,25
2019-01-03 14:04:50,,2304515,20
2019-01-03 14:05:29,,2304519,20
2019-01-03 14:08:24,,2304519,25
2019-01-03 14:13:33,,2304519,20
2019-01-03 14:22:31,,2304519,20
2019-01-03 14:09:16,,2304519,20
2019-01-03 14:12:41,,2304519,25
2019-01-03 14:17:46,,2304519,25
2019-01-03 14:18:52,,2304519,20
2019-01-03 14:21:42,,2304519,25
2019-01-03 14:26:57,,2304519,25
2019-01-03 14:27:44,,2304519,20
2019-01-03 14:30:13,,2304519,20
2019-01-03 14:29:24,,2304519,25
2019-01-03 14:36:05,,2304519,25
2019-01-03 14:46:31,,2304515,25
2019-01-03 14:47:28,,2304519,20
2019-01-03 14:49:28,,2304515,20
```

**2019.zip::tblDailySummary_2019_01.csv**

```text
TimeStamp,StationId,StationGroupId,SamplePeriode,Samples,Energy,MeanPower,CapacityFactor,NacelleWind,Availabillity,MetWindSpeed,GridExportEnergy,GridImportEnergy,GridReactiveImportEnergy,GridNetto,Gri
2019-01-01,91,3,1440,100,,,,,,,598464.0,0.0,135008.0,598464.0,,,,,,,,,,,,,,,,,,,,,1626021.0,782273664.0,,175883744.0,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,95,,,,
2019-01-01,2304510,1,1440,100,30100.0,1254.2650146484375,54.52898025512695,9.106366157531738,100.0,,,,,,0.0,100.0,95.4000015258789,38102476.0,24.0,24.0,0.0,0.0,23.290000915527344,18.809999465942383,,,
2019-01-01,2304511,1,1440,100,26464.0,1102.635986328125,47.94203186035156,8.422107696533203,100.0,,,,,,0.0,100.0,96.5,35194808.0,24.0,24.0,0.0,0.0,22.329999923706055,18.889999389648438,,,,8.3000001907
2019-01-01,2304512,1,1440,100,32792.0,1366.281982421875,59.405799865722656,9.850889205932617,100.0,,,,,,0.0,100.0,97.80000305175781,39944408.0,24.0,24.0,0.0,0.0,23.940000534057617,22.049999237060547,,
2019-01-01,2304513,1,1440,100,29980.0,1249.239013671875,54.31159973144531,9.265968322753906,100.0,,,,,,0.0,100.0,96.19999694824219,40583140.0,24.0,24.0,0.0,0.0,23.079999923706055,20.6299991607666,,,,9
2019-01-01,2304514,1,1440,100,27172.0,1132.2030029296875,49.224639892578125,8.89276123046875,100.0,,,,,,0.0,100.0,98.30000305175781,36232608.0,24.0,24.0,0.0,0.0,23.229999542236328,21.06999969482422,,,
2019-01-01,2304515,1,1440,100,21692.0,903.7589111328125,39.29710006713867,7.985263824462891,100.0,,,,,,0.0,100.0,97.4000015258789,28367576.0,24.0,24.0,0.0,0.0,23.6299991607666,20.84000015258789,,,,7.9
2019-01-01,2304516,1,1440,100,31296.0,1304.031982421875,56.695648193359375,9.979602813720703,100.0,,,,,,0.0,100.0,97.9000015258789,43059876.0,24.0,24.0,0.0,0.0,23.940000534057617,22.309999465942383,,,
2019-01-01,2304517,1,1440,100,27860.0,1160.8800048828125,50.47101974487305,8.98428726196289,100.0,,,,,,0.0,100.0,98.0,37589420.0,24.0,24.0,0.0,0.0,23.729999542236328,21.450000762939453,,,,8.8999996185
2019-01-01,2304518,1,1440,100,30284.0,1261.738037109375,54.86231994628906,9.107815742492676,100.0,,,,,,0.0,100.0,96.5,40028856.0,24.0,24.0,0.0,0.0,23.90999984741211,22.010000228881836,,,,9.0,20.100000
2019-01-01,2304519,1,1440,100,23078.0,961.67626953125,41.80796813964844,8.041964530944824,100.0,,,,,,0.0,100.0,97.80000305175781,28344198.0,24.0,24.0,0.0,0.0,23.709999084472656,19.889999389648438,,,,7
2019-01-01,2304520,1,1440,100,30912.0,1288.0980224609375,56.0,9.52133560180664,100.0,,,,,,0.0,100.0,96.5,42503216.0,24.0,24.0,0.0,0.0,23.860000610351562,22.149999618530273,,,,9.399999618530273,20.8999
2019-01-01,2304521,1,1440,100,30712.0,1279.676025390625,55.63768005371094,9.783807754516602,100.0,,,,,,0.0,100.0,96.5999984741211,44476392.0,24.0,24.0,0.0,0.0,23.90999984741211,21.770000457763672,,,,9
2019-01-01,2304522,1,1440,100,31672.0,1319.677001953125,57.376808166503906,9.662875175476074,100.0,,,,,,0.0,100.0,98.69999694824219,49169220.0,24.0,24.0,0.0,0.0,23.940000534057617,23.3799991607666,,,,
2019-01-01,2304523,1,1440,100,30896.0,1287.240966796875,55.97101974487305,9.42966365814209,100.0,,,,,,0.0,100.0,98.19999694824219,44565688.0,24.0,24.0,0.0,0.0,23.979999542236328,21.84000015258789,,,,9
2019-01-01,2304524,1,1440,100,21362.0,889.980712890625,38.69927978515625,7.630733013153076,100.0,,,,,,0.0,100.0,96.30000305175781,27912108.0,24.0,24.0,0.0,0.0,23.530000686645508,20.020000457763672,,,,
2019-01-01,2304525,1,1440,100,23788.0,991.1978759765625,43.094200134277344,8.023213386535645,100.0,,,,,,0.0,100.0,98.0999984741211,30517276.0,24.0,24.0,0.0,0.0,23.93000030517578,21.489999771118164,,,,
2019-01-01,2304526,1,1440,100,29490.0,1228.863037109375,53.42390823364258,8.947972297668457,100.0,,,,,,0.0,100.0,96.0999984741211,30366668.0,24.0,24.0,0.0,0.0,23.920000076293945,22.25,,,,8.89999961853
2019-01-01,2304527,1,1440,100,22598.0,941.61279296875,40.93840026855469,7.845948219299316,99.875,,,,,,0.0,99.80000305175781,98.5,29714738.0,24.0,23.959999084472656,0.029999999329447746,0.0,23.20999908
2019-01-01,2304528,1,1440,100,34420.0,1434.3280029296875,62.35506820678711,10.116379737854004,100.0,,,,,,0.0,100.0,98.5,39186264.0,24.0,24.0,0.0,0.0,23.940000534057617,23.18000030517578,,,,10.0,21.299
2019-01-01,2304529,1,1440,100,32068.0,1336.2569580078125,58.094200134277344,9.411446571350098,100.0,,,,,,0.0,100.0,97.5,38039128.0,24.0,24.0,0.0,0.0,23.940000534057617,22.739999771118164,,,,9.30000019
2019-01-01,2304530,1,1440,100,33160.0,1381.7060546875,60.07246017456055,9.864992141723633,100.0,,,,,,0.0,100.0,98.69999694824219,41607472.0,24.0,24.0,0.0,0.0,23.940000534057617,23.329999923706055,,,,9
2019-01-02,91,3,1440,100,,,,,,,20224.0,3242.0,80.0,16982.0,,,,,,,,,,,,,,,,,,,,,1629263.0,782293888.0,,175883824.0,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,95,,,,,,,
2019-01-02,2304510,1,1440,100,980.0,40.84783172607422,1.7753620147705078,3.125394105911255,100.0,,,,,,0.0,100.0,95.4000015258789,38103456.0,24.0,24.0,0.0,0.0,11.199999809265137,2.109999895095825,,,,6.
2019-01-02,2304511,1,1440,100,864.0,35.90026092529297,1.5652170181274414,3.111717939376831,100.0,,,,,,0.0,100.0,96.5,35195672.0,24.0,24.0,0.0,0.0,9.779999732971191,1.9700000286102295,,,,5.699999809265
2019-01-02,2304512,1,1440,100,984.0,41.0407600402832,1.782608985900879,3.1621949672698975,100.0,,,,,,0.0,100.0,97.80000305175781,39945392.0,24.0,24.0,0.0,0.0,12.279999732971191,1.7100000381469727,,,,6
2019-01-02,2304513,1,1440,100,824.0,34.314090728759766,1.4927539825439453,3.0599679946899414,100.0,,,,,,0.0,100.0,96.19999694824219,40583964.0,24.0,23.989999771118164,0.0,0.0,10.619999885559082,1.5700
2019-01-02,2304514,1,1440,100,752.0,31.294330596923828,1.362318992614746,3.0705161094665527,100.0,,,,,,0.0,100.0,98.30000305175781,36233360.0,24.0,24.0,0.0,0.0,9.90999984741211,1.590000033378601,,,,5.
2019-01-02,2304515,1,1440,100,500.0,20.892169952392578,0.9057971239089966,2.729212999343872,100.0,,,,,,0.0,100.0,97.4000015258789,28368076.0,24.0,24.0,0.0,0.0,7.400000095367432,0.8700000047683716,,,,5
```

**2019.zip::tblSCTurbine_2019_01.csv**

```text
TimeStamp,StationId,wtc_CurTime_endvalue,wtc_SecAnemo_min,wtc_SecAnemo_max,wtc_SecAnemo_mean,wtc_SecAnemo_stddev,wtc_YawPos_min,wtc_YawPos_max,wtc_YawPos_mean,wtc_YawPos_stddev,wtc_GenRpm_min,wtc_GenR
2019-01-01 00:00:00,2304510,2018-12-31 23:59:58,9.510000228881836,20.34000015258789,13.72035026550293,1.704313039779663,304.8999938964844,314.5,309.48199462890625,3.783811092376709,1440.0,1627.5999755
2019-01-01 00:00:00,2304511,2018-12-31 23:59:59,8.199999809265137,21.959999084472656,14.337639808654785,2.3080010414123535,267.6000061035156,281.8999938964844,272.4891052246094,3.092231035232544,1461.
2019-01-01 00:00:00,2304512,2018-12-31 23:59:58,10.109999656677246,23.239999771118164,15.195509910583496,2.352008104324341,283.8999938964844,293.79998779296875,287.1640930175781,2.485790967941284,1465
2019-01-01 00:00:00,2304513,2018-12-31 23:59:59,8.420000076293945,21.559999465942383,14.54951000213623,2.243514060974121,286.79998779296875,294.0,289.63031005859375,2.4013099670410156,1443.90002441406
2019-01-01 00:00:00,2304514,2018-12-31 23:59:59,7.909999847412109,23.010000228881836,13.679329872131348,2.537709951400757,268.3999938964844,276.0,270.7356872558594,1.9032829999923706,1410.400024414062
2019-01-01 00:00:00,2304515,2018-12-31 23:59:59,7.039999961853027,20.43000030517578,13.53756046295166,2.0494489669799805,278.70001220703125,288.6000061035156,285.2210998535156,2.9022369384765625,1431.
2019-01-01 00:00:00,2304516,2018-12-31 23:59:59,9.699999809265137,21.020000457763672,14.923450469970703,1.8921869993209839,300.5,304.29998779296875,302.1448974609375,1.4971139430999756,1454.1999511718
2019-01-01 00:00:00,2304517,2018-12-31 23:59:58,9.319999694824219,22.649999618530273,14.182319641113281,2.27616810798645,284.0,290.79998779296875,287.4176025390625,1.8612459897994995,1456.5,1615.40002
2019-01-01 00:00:00,2304518,2018-12-31 23:59:59,11.369999885559082,23.020000457763672,15.790820121765137,2.0295729637145996,269.6000061035156,275.3999938964844,272.5841979980469,1.7489529848098755,147
2019-01-01 00:00:00,2304519,2018-12-31 23:59:58,7.320000171661377,18.84000015258789,12.516349792480469,2.045233964920044,299.70001220703125,302.3999938964844,302.018310546875,0.853988528251648,1232.90
2019-01-01 00:00:00,2304520,2018-12-31 23:59:59,9.84000015258789,24.209999084472656,14.93554973602295,1.8986129760742188,302.8999938964844,308.6000061035156,305.89691162109375,1.9806489944458008,1465.
2019-01-01 00:00:00,2304521,2018-12-31 23:59:58,7.639999866485596,20.399999618530273,13.502820014953613,2.052341938018799,83.5,89.9000015258789,87.41499328613281,2.0721089839935303,1445.0,1628.5,1545.
2019-01-01 00:00:00,2304522,2018-12-31 23:59:59,10.699999809265137,23.65999984741211,16.212509155273438,2.689455986022949,280.3999938964844,286.29998779296875,283.83740234375,1.9601349830627441,1474.6
2019-01-01 00:00:00,2304523,2018-12-31 23:59:59,9.6899995803833,19.360000610351562,14.30685043334961,1.492493987083435,293.20001220703125,298.1000061035156,295.6169128417969,1.4550960063934326,1457.30
2019-01-01 00:00:00,2304524,2018-12-31 23:59:59,7.03000020980835,19.979999542236328,12.580869674682617,2.244101047515869,291.1000061035156,298.8999938964844,294.7315979003906,2.4066460132598877,1290.5
2019-01-01 00:00:00,2304525,2018-12-31 23:59:59,8.539999961853027,20.25,13.17432975769043,2.2855019569396973,197.3000030517578,203.89999389648438,200.60150146484375,2.010474920272827,1257.099975585937
2019-01-01 00:00:00,2304526,2018-12-31 23:59:58,8.180000305175781,17.6200008392334,12.300649642944336,1.732532024383545,294.6000061035156,304.0,300.7030944824219,2.5359880924224854,1409.5,1610.3000488
2019-01-01 00:00:00,2304527,2018-12-31 23:59:59,8.380000114440918,17.389999389648438,12.496159553527832,1.383162021636963,282.5,285.8999938964844,283.58660888671875,1.318079948425293,1435.800048828125
2019-01-01 00:00:00,2304528,2018-12-31 23:59:58,8.130000114440918,20.989999771118164,14.021300315856934,2.243726968765259,275.70001220703125,280.1000061035156,277.0943908691406,1.9065109491348267,1389
2019-01-01 00:00:00,2304529,2018-12-31 23:59:58,5.769999980926514,19.860000610351562,12.409059524536133,2.2166099548339844,289.3999938964844,297.20001220703125,293.0105895996094,2.3810811042785645,120
2019-01-01 00:00:00,2304530,2018-12-31 23:59:59,8.130000114440918,20.229999542236328,13.049220085144043,2.149549961090088,279.3999938964844,283.3999938964844,282.4371032714844,1.0803500413894653,1399.
2019-01-01 00:10:00,2304510,2019-01-01 00:09:59,6.5,18.959999084472656,13.331270217895508,2.0113658905029297,304.70001220703125,308.8999938964844,305.21551513671875,1.30315101146698,1318.5,1639.099975
2019-01-01 00:10:00,2304511,2019-01-01 00:09:59,8.520000457763672,20.8700008392334,14.288559913635254,1.9522969722747803,265.29998779296875,276.70001220703125,269.6377868652344,2.837002992630005,1439.
2019-01-01 00:10:00,2304512,2019-01-01 00:09:58,7.53000020980835,17.3799991607666,12.903189659118652,1.5878980159759521,282.3999938964844,291.20001220703125,285.4381103515625,2.852626085281372,1424.0,
2019-01-01 00:10:00,2304513,2019-01-01 00:09:59,7.929999828338623,19.8799991607666,12.275690078735352,2.2099809646606445,289.0,292.3999938964844,289.85888671875,1.1332950592041016,1418.800048828125,16
2019-01-01 00:10:00,2304514,2019-01-01 00:09:59,4.960000038146973,18.90999984741211,11.791529655456543,2.2568750381469727,263.5,269.5,266.776611328125,2.1050798892974854,1150.0,1616.5,1480.98498535156
2019-01-01 00:10:00,2304515,2019-01-01 00:09:59,5.130000114440918,17.950000762939453,9.912320137023926,2.453969955444336,281.5,296.0,287.24578857421875,3.2843940258026123,882.7999877929688,1612.800048
2019-01-01 00:10:00,2304516,2019-01-01 00:09:58,9.640000343322754,23.1299991607666,14.074700355529785,2.0058629512786865,300.70001220703125,304.5,302.2786865234375,1.731997013092041,1469.0,1620.099975
2019-01-01 00:10:00,2304517,2019-01-01 00:09:58,8.25,20.030000686645508,13.522270202636719,2.332515001296997,285.0,289.79998779296875,287.6824035644531,1.6531100273132324,1443.5,1620.0999755859375,153
```

**Hill_of_Towie_AeroUp_install_dates.csv**

```text
Turbine,First date of AeroUp works,Last date of AeroUp works
T01,2022-07-23,2022-08-01
T02,2022-07-18,2022-07-28
T03,2022-07-28,2022-08-14
T04,2022-07-31,2022-09-10
T05,2022-07-16,2022-07-22
T06,2022-07-16,2023-04-15
T07,2022-09-20,2023-05-25
T08,2022-08-08,2022-09-21
T09,2022-09-13,2022-10-03
T10,2022-08-04,2023-04-26
T11,2022-09-09,2023-05-18
T12,2022-09-01,2023-05-09
T13,2021-09-23,2021-09-29
T14,2022-08-30,2022-10-03
T15,2022-07-14,2023-05-26
T16,2022-08-27,2023-04-15
T17,2022-08-10,2022-08-27
T18,2022-08-22,2022-09-21
T19,2022-08-11,2022-08-23
T20,2022-08-13,2023-04-20
T21,2022-08-21,2022-09-01
```

**Hill_of_Towie_ShutdownDuration.zip::ShutdownDuration.csv**

```text
TimeStamp_StartFormat,TurbineName,ShutdownDuration
2016-01-01 00:00:00+00:00,T01,0
2016-01-01 00:00:00+00:00,T02,0
2016-01-01 00:00:00+00:00,T03,0
2016-01-01 00:00:00+00:00,T04,0
2016-01-01 00:00:00+00:00,T05,0
2016-01-01 00:00:00+00:00,T06,600
2016-01-01 00:00:00+00:00,T07,0
2016-01-01 00:00:00+00:00,T08,0
2016-01-01 00:00:00+00:00,T09,0
2016-01-01 00:00:00+00:00,T10,0
2016-01-01 00:00:00+00:00,T11,0
2016-01-01 00:00:00+00:00,T12,0
2016-01-01 00:00:00+00:00,T13,0
2016-01-01 00:00:00+00:00,T14,0
2016-01-01 00:00:00+00:00,T15,0
2016-01-01 00:00:00+00:00,T16,0
2016-01-01 00:00:00+00:00,T17,0
2016-01-01 00:00:00+00:00,T18,0
2016-01-01 00:00:00+00:00,T19,0
2016-01-01 00:00:00+00:00,T20,0
2016-01-01 00:00:00+00:00,T21,0
2016-01-01 00:10:00+00:00,T01,0
2016-01-01 00:10:00+00:00,T02,0
2016-01-01 00:10:00+00:00,T03,0
2016-01-01 00:10:00+00:00,T04,0
2016-01-01 00:10:00+00:00,T05,0
2016-01-01 00:10:00+00:00,T06,600
2016-01-01 00:10:00+00:00,T07,0
2016-01-01 00:10:00+00:00,T08,0
```

## Member listing (319 of 319)

| archive | member | kind | uncompressed (MB) | compressed (MB) |
| --- | --- | --- | --- | --- |
| 2019.zip | tblAlarmLog_2019_01.csv | alarm_log | 0.823 | 0.125 |
| 2019.zip | tblAlarmLog_2019_02.csv | alarm_log | 1.4 | 0.206 |
| 2019.zip | tblAlarmLog_2019_03.csv | alarm_log | 0.952 | 0.142 |
| 2019.zip | tblAlarmLog_2019_04.csv | alarm_log | 2.025 | 0.296 |
| 2019.zip | tblAlarmLog_2019_05.csv | alarm_log | 2.823 | 0.407 |
| 2019.zip | tblAlarmLog_2019_06.csv | alarm_log | 2.369 | 0.344 |
| 2019.zip | tblAlarmLog_2019_07.csv | alarm_log | 3.168 | 0.457 |
| 2019.zip | tblAlarmLog_2019_08.csv | alarm_log | 2.807 | 0.401 |
| 2019.zip | tblAlarmLog_2019_09.csv | alarm_log | 1.965 | 0.284 |
| 2019.zip | tblAlarmLog_2019_10.csv | alarm_log | 1.435 | 0.204 |
| 2019.zip | tblAlarmLog_2019_11.csv | alarm_log | 1.306 | 0.19 |
| 2019.zip | tblAlarmLog_2019_12.csv | alarm_log | 1.252 | 0.185 |
| 2019.zip | tblDailySummary_2019_01.csv | other | 0.599 | 0.116 |
| 2019.zip | tblDailySummary_2019_02.csv | other | 0.547 | 0.11 |
| 2019.zip | tblDailySummary_2019_03.csv | other | 0.601 | 0.117 |
| 2019.zip | tblDailySummary_2019_04.csv | other | 0.596 | 0.118 |
| 2019.zip | tblDailySummary_2019_05.csv | other | 0.616 | 0.126 |
| 2019.zip | tblDailySummary_2019_06.csv | other | 0.601 | 0.121 |
| 2019.zip | tblDailySummary_2019_07.csv | other | 0.626 | 0.129 |
| 2019.zip | tblDailySummary_2019_08.csv | other | 0.621 | 0.126 |
| 2019.zip | tblDailySummary_2019_09.csv | other | 0.592 | 0.116 |
| 2019.zip | tblDailySummary_2019_10.csv | other | 0.604 | 0.118 |
| 2019.zip | tblDailySummary_2019_11.csv | other | 0.589 | 0.115 |
| 2019.zip | tblDailySummary_2019_12.csv | other | 0.594 | 0.112 |
| 2019.zip | tblGridScientific_2019_01.csv | other | 0.961 | 0.166 |
| 2019.zip | tblGridScientific_2019_02.csv | other | 0.864 | 0.154 |
| 2019.zip | tblGridScientific_2019_03.csv | other | 0.957 | 0.171 |
| 2019.zip | tblGridScientific_2019_04.csv | other | 0.925 | 0.158 |
| 2019.zip | tblGridScientific_2019_05.csv | other | 0.955 | 0.155 |
| 2019.zip | tblGridScientific_2019_06.csv | other | 0.926 | 0.153 |
| 2019.zip | tblGridScientific_2019_07.csv | other | 0.956 | 0.154 |
| 2019.zip | tblGridScientific_2019_08.csv | other | 0.961 | 0.158 |
| 2019.zip | tblGridScientific_2019_09.csv | other | 0.93 | 0.159 |
| 2019.zip | tblGridScientific_2019_10.csv | other | 0.966 | 0.166 |
| 2019.zip | tblGridScientific_2019_11.csv | other | 0.93 | 0.156 |
| 2019.zip | tblGridScientific_2019_12.csv | other | 0.966 | 0.169 |
| 2019.zip | tblGrid_2019_01.csv | other | 1.094 | 0.239 |
| 2019.zip | tblGrid_2019_02.csv | other | 0.984 | 0.214 |
| 2019.zip | tblGrid_2019_03.csv | other | 1.087 | 0.239 |
| 2019.zip | tblGrid_2019_04.csv | other | 1.056 | 0.229 |
| 2019.zip | tblGrid_2019_05.csv | other | 1.084 | 0.227 |
| 2019.zip | tblGrid_2019_06.csv | other | 1.05 | 0.219 |
| 2019.zip | tblGrid_2019_07.csv | other | 1.089 | 0.225 |
| 2019.zip | tblGrid_2019_08.csv | other | 1.096 | 0.227 |
| 2019.zip | tblGrid_2019_09.csv | other | 1.054 | 0.22 |
| 2019.zip | tblGrid_2019_10.csv | other | 1.084 | 0.229 |
| 2019.zip | tblGrid_2019_11.csv | other | 1.05 | 0.227 |
| 2019.zip | tblGrid_2019_12.csv | other | 1.084 | 0.234 |
| 2019.zip | tblSCTurbine_2019_01.csv | scada_10min | 135.1 | 30.46 |
| 2019.zip | tblSCTurbine_2019_02.csv | scada_10min | 121.2 | 27.77 |
| 2019.zip | tblSCTurbine_2019_03.csv | scada_10min | 133.6 | 31.2 |
| 2019.zip | tblSCTurbine_2019_04.csv | scada_10min | 130.5 | 29.69 |
| 2019.zip | tblSCTurbine_2019_05.csv | scada_10min | 134.7 | 30.73 |
| 2019.zip | tblSCTurbine_2019_06.csv | scada_10min | 131 | 29.88 |
| 2019.zip | tblSCTurbine_2019_07.csv | scada_10min | 132.8 | 30.01 |
| 2019.zip | tblSCTurbine_2019_08.csv | scada_10min | 134.2 | 30.28 |
| 2019.zip | tblSCTurbine_2019_09.csv | scada_10min | 129 | 29.2 |
| 2019.zip | tblSCTurbine_2019_10.csv | scada_10min | 134.8 | 31.14 |
| 2019.zip | tblSCTurbine_2019_11.csv | scada_10min | 131.6 | 29.76 |
| 2019.zip | tblSCTurbine_2019_12.csv | scada_10min | 135.7 | 31.66 |
| 2019.zip | tblSCTurCount_2019_01.csv | scada_10min | 52.1 | 9.055 |
| 2019.zip | tblSCTurCount_2019_02.csv | scada_10min | 47.32 | 8.255 |
| 2019.zip | tblSCTurCount_2019_03.csv | scada_10min | 51.67 | 9.095 |
| 2019.zip | tblSCTurCount_2019_04.csv | scada_10min | 50.81 | 8.614 |
| 2019.zip | tblSCTurCount_2019_05.csv | scada_10min | 52.07 | 8.703 |
| 2019.zip | tblSCTurCount_2019_06.csv | scada_10min | 50.83 | 8.587 |
| 2019.zip | tblSCTurCount_2019_07.csv | scada_10min | 52.47 | 8.7 |
| 2019.zip | tblSCTurCount_2019_08.csv | scada_10min | 52.1 | 8.741 |
| 2019.zip | tblSCTurCount_2019_09.csv | scada_10min | 49.57 | 8.459 |
| 2019.zip | tblSCTurCount_2019_10.csv | scada_10min | 52.2 | 8.904 |
| 2019.zip | tblSCTurCount_2019_11.csv | scada_10min | 50.88 | 8.53 |
| 2019.zip | tblSCTurCount_2019_12.csv | scada_10min | 50.88 | 8.938 |
| 2019.zip | tblSCTurDigiIn_2019_01.csv | scada_10min | 27.14 | 1.193 |
| 2019.zip | tblSCTurDigiIn_2019_02.csv | scada_10min | 24.44 | 1.081 |
| 2019.zip | tblSCTurDigiIn_2019_03.csv | scada_10min | 27.11 | 1.222 |
| 2019.zip | tblSCTurDigiIn_2019_04.csv | scada_10min | 26.24 | 1.154 |
| 2019.zip | tblSCTurDigiIn_2019_05.csv | scada_10min | 27.14 | 1.186 |
| 2019.zip | tblSCTurDigiIn_2019_06.csv | scada_10min | 26.27 | 1.164 |
| 2019.zip | tblSCTurDigiIn_2019_07.csv | scada_10min | 26.91 | 1.166 |
| 2019.zip | tblSCTurDigiIn_2019_08.csv | scada_10min | 27.04 | 1.17 |
| 2019.zip | tblSCTurDigiIn_2019_09.csv | scada_10min | 25.92 | 1.126 |
| 2019.zip | tblSCTurDigiIn_2019_10.csv | scada_10min | 27.01 | 1.176 |
| 2019.zip | tblSCTurDigiIn_2019_11.csv | scada_10min | 26.21 | 1.125 |
| 2019.zip | tblSCTurDigiIn_2019_12.csv | scada_10min | 27.13 | 1.203 |
| 2019.zip | tblSCTurDigiOut_2019_01.csv | scada_10min | 32.41 | 0.871 |
| 2019.zip | tblSCTurDigiOut_2019_02.csv | scada_10min | 29.27 | 0.822 |
| 2019.zip | tblSCTurDigiOut_2019_03.csv | scada_10min | 18.96 | 0.782 |
| 2019.zip | tblSCTurDigiOut_2019_04.csv | scada_10min | 18.33 | 0.774 |
| 2019.zip | tblSCTurDigiOut_2019_05.csv | scada_10min | 18.97 | 0.835 |
| 2019.zip | tblSCTurDigiOut_2019_06.csv | scada_10min | 18.36 | 0.786 |
| 2019.zip | tblSCTurDigiOut_2019_07.csv | scada_10min | 18.82 | 0.814 |
| 2019.zip | tblSCTurDigiOut_2019_08.csv | scada_10min | 18.92 | 0.807 |
| 2019.zip | tblSCTurDigiOut_2019_09.csv | scada_10min | 18.13 | 0.747 |
| 2019.zip | tblSCTurDigiOut_2019_10.csv | scada_10min | 32.35 | 0.884 |
| 2019.zip | tblSCTurDigiOut_2019_11.csv | scada_10min | 18.31 | 0.711 |
| 2019.zip | tblSCTurDigiOut_2019_12.csv | scada_10min | 18.97 | 0.752 |
| 2019.zip | tblSCTurFlag_2019_01.csv | scada_10min | 11.32 | 0.496 |
| 2019.zip | tblSCTurFlag_2019_02.csv | scada_10min | 10.22 | 0.474 |
| 2019.zip | tblSCTurFlag_2019_03.csv | scada_10min | 11.33 | 0.476 |
| 2019.zip | tblSCTurFlag_2019_04.csv | scada_10min | 10.92 | 0.531 |
| 2019.zip | tblSCTurFlag_2019_05.csv | scada_10min | 11.22 | 0.574 |
| 2019.zip | tblSCTurFlag_2019_06.csv | scada_10min | 10.89 | 0.555 |
| 2019.zip | tblSCTurFlag_2019_07.csv | scada_10min | 11.13 | 0.568 |
| 2019.zip | tblSCTurFlag_2019_08.csv | scada_10min | 11.28 | 0.566 |
| 2019.zip | tblSCTurFlag_2019_09.csv | scada_10min | 10.81 | 0.517 |
| 2019.zip | tblSCTurFlag_2019_10.csv | scada_10min | 14.04 | 0.512 |
| 2019.zip | tblSCTurFlag_2019_11.csv | scada_10min | 10.88 | 0.5 |
| 2019.zip | tblSCTurFlag_2019_12.csv | scada_10min | 11.3 | 0.493 |
| 2019.zip | tblSCTurGrid_2019_01.csv | scada_10min | 68.87 | 21.23 |
| 2019.zip | tblSCTurGrid_2019_02.csv | scada_10min | 62.2 | 19.21 |
| 2019.zip | tblSCTurGrid_2019_03.csv | scada_10min | 68.98 | 20.9 |
| 2019.zip | tblSCTurGrid_2019_04.csv | scada_10min | 66.51 | 20.7 |
| 2019.zip | tblSCTurGrid_2019_05.csv | scada_10min | 68.55 | 21.51 |
| 2019.zip | tblSCTurGrid_2019_06.csv | scada_10min | 66.36 | 20.73 |
| 2019.zip | tblSCTurGrid_2019_07.csv | scada_10min | 67.75 | 21.16 |
| 2019.zip | tblSCTurGrid_2019_08.csv | scada_10min | 68.17 | 21.26 |
| 2019.zip | tblSCTurGrid_2019_09.csv | scada_10min | 65.32 | 20.27 |
| 2019.zip | tblSCTurGrid_2019_10.csv | scada_10min | 68.19 | 20.96 |
| 2019.zip | tblSCTurGrid_2019_11.csv | scada_10min | 66.41 | 20.68 |
| 2019.zip | tblSCTurGrid_2019_12.csv | scada_10min | 68.58 | 21.16 |
| 2019.zip | tblSCTurIntern_2019_01.csv | scada_10min | 23.23 | 5.355 |
| 2019.zip | tblSCTurIntern_2019_02.csv | scada_10min | 20.83 | 4.921 |
| 2019.zip | tblSCTurIntern_2019_03.csv | scada_10min | 23 | 5.583 |
| 2019.zip | tblSCTurIntern_2019_04.csv | scada_10min | 22.47 | 5.296 |
| 2019.zip | tblSCTurIntern_2019_05.csv | scada_10min | 23.24 | 5.478 |
| 2019.zip | tblSCTurIntern_2019_06.csv | scada_10min | 22.54 | 5.276 |
| 2019.zip | tblSCTurIntern_2019_07.csv | scada_10min | 22.94 | 5.417 |
| 2019.zip | tblSCTurIntern_2019_08.csv | scada_10min | 23.17 | 5.381 |
| 2019.zip | tblSCTurIntern_2019_09.csv | scada_10min | 22.27 | 5.141 |
| 2019.zip | tblSCTurIntern_2019_10.csv | scada_10min | 23.18 | 5.41 |
| 2019.zip | tblSCTurIntern_2019_11.csv | scada_10min | 22.67 | 5.14 |
| 2019.zip | tblSCTurIntern_2019_12.csv | scada_10min | 23.28 | 5.431 |
| 2019.zip | tblSCTurPress_2019_01.csv | scada_10min | 55.02 | 15.38 |
| 2019.zip | tblSCTurPress_2019_02.csv | scada_10min | 49.52 | 14.06 |
| 2019.zip | tblSCTurPress_2019_03.csv | scada_10min | 54.84 | 15.52 |
| 2019.zip | tblSCTurPress_2019_04.csv | scada_10min | 53.73 | 15.27 |
| 2019.zip | tblSCTurPress_2019_05.csv | scada_10min | 55.55 | 15.79 |
| 2019.zip | tblSCTurPress_2019_06.csv | scada_10min | 53.81 | 15.37 |
| 2019.zip | tblSCTurPress_2019_07.csv | scada_10min | 54.48 | 15.4 |
| 2019.zip | tblSCTurPress_2019_08.csv | scada_10min | 54.48 | 15.57 |
| 2019.zip | tblSCTurPress_2019_09.csv | scada_10min | 52.58 | 15 |
| 2019.zip | tblSCTurPress_2019_10.csv | scada_10min | 54.92 | 15.61 |
| 2019.zip | tblSCTurPress_2019_11.csv | scada_10min | 53.32 | 14.8 |
| 2019.zip | tblSCTurPress_2019_12.csv | scada_10min | 55.56 | 15.47 |
| 2019.zip | tblSCTurTemp_2019_01.csv | scada_10min | 107.8 | 35.03 |
| 2019.zip | tblSCTurTemp_2019_02.csv | scada_10min | 101 | 33.78 |
| 2019.zip | tblSCTurTemp_2019_03.csv | scada_10min | 111.6 | 37.32 |
| 2019.zip | tblSCTurTemp_2019_04.csv | scada_10min | 107.5 | 35.66 |
| 2019.zip | tblSCTurTemp_2019_05.csv | scada_10min | 109.9 | 35.94 |
| 2019.zip | tblSCTurTemp_2019_06.csv | scada_10min | 108.4 | 35.85 |
| 2019.zip | tblSCTurTemp_2019_07.csv | scada_10min | 109.2 | 35.42 |
| 2019.zip | tblSCTurTemp_2019_08.csv | scada_10min | 110.9 | 36.27 |
| 2019.zip | tblSCTurTemp_2019_09.csv | scada_10min | 106.8 | 35.25 |
| 2019.zip | tblSCTurTemp_2019_10.csv | scada_10min | 110.7 | 36.62 |
| 2019.zip | tblSCTurTemp_2019_11.csv | scada_10min | 104.2 | 33.64 |
| 2019.zip | tblSCTurTemp_2019_12.csv | scada_10min | 111.1 | 36.87 |
| 2023.zip | tblAlarmLog_2023_01.csv | alarm_log | 0.532 | 0.081 |
| 2023.zip | tblAlarmLog_2023_02.csv | alarm_log | 0.639 | 0.098 |
| 2023.zip | tblAlarmLog_2023_03.csv | alarm_log | 1.211 | 0.18 |
| 2023.zip | tblAlarmLog_2023_04.csv | alarm_log | 1.087 | 0.164 |
| 2023.zip | tblAlarmLog_2023_05.csv | alarm_log | 1.436 | 0.214 |
| 2023.zip | tblAlarmLog_2023_06.csv | alarm_log | 1.558 | 0.226 |
| 2023.zip | tblAlarmLog_2023_07.csv | alarm_log | 1.141 | 0.169 |
| 2023.zip | tblAlarmLog_2023_08.csv | alarm_log | 1.329 | 0.196 |
| 2023.zip | tblAlarmLog_2023_09.csv | alarm_log | 0.965 | 0.145 |
| 2023.zip | tblAlarmLog_2023_10.csv | alarm_log | 0.63 | 0.094 |
| 2023.zip | tblAlarmLog_2023_11.csv | alarm_log | 0.729 | 0.109 |
| 2023.zip | tblAlarmLog_2023_12.csv | alarm_log | 0.62 | 0.091 |
| 2023.zip | tblDailySummary_2023_01.csv | other | 0.728 | 0.124 |
| 2023.zip | tblDailySummary_2023_02.csv | other | 0.67 | 0.121 |
| 2023.zip | tblDailySummary_2023_03.csv | other | 0.744 | 0.132 |
| 2023.zip | tblDailySummary_2023_04.csv | other | 0.721 | 0.129 |
| 2023.zip | tblDailySummary_2023_05.csv | other | 0.745 | 0.138 |
| 2023.zip | tblDailySummary_2023_06.csv | other | 0.715 | 0.126 |
| 2023.zip | tblDailySummary_2023_07.csv | other | 0.749 | 0.133 |
| 2023.zip | tblDailySummary_2023_08.csv | other | 0.741 | 0.132 |
| 2023.zip | tblDailySummary_2023_09.csv | other | 0.719 | 0.127 |
| 2023.zip | tblDailySummary_2023_10.csv | other | 0.742 | 0.128 |
| 2023.zip | tblDailySummary_2023_11.csv | other | 0.711 | 0.126 |
| 2023.zip | tblDailySummary_2023_12.csv | other | 0.729 | 0.131 |
| 2023.zip | tblGridScientific_2023_01.csv | other | 1.028 | 0.399 |
| 2023.zip | tblGridScientific_2023_02.csv | other | 0.927 | 0.353 |
| 2023.zip | tblGridScientific_2023_03.csv | other | 1.026 | 0.401 |
| 2023.zip | tblGridScientific_2023_04.csv | other | 0.994 | 0.388 |
| 2023.zip | tblGridScientific_2023_05.csv | other | 1.027 | 0.397 |
| 2023.zip | tblGridScientific_2023_06.csv | other | 0.993 | 0.385 |
| 2023.zip | tblGridScientific_2023_07.csv | other | 1.027 | 0.399 |
| 2023.zip | tblGridScientific_2023_08.csv | other | 1.027 | 0.399 |
| 2023.zip | tblGridScientific_2023_09.csv | other | 0.993 | 0.39 |
| 2023.zip | tblGridScientific_2023_10.csv | other | 1.026 | 0.399 |
| 2023.zip | tblGridScientific_2023_11.csv | other | 0.993 | 0.385 |
| 2023.zip | tblGridScientific_2023_12.csv | other | 1.027 | 0.396 |
| 2023.zip | tblGrid_2023_01.csv | other | 1.146 | 0.345 |
| 2023.zip | tblGrid_2023_02.csv | other | 1.033 | 0.303 |
| 2023.zip | tblGrid_2023_03.csv | other | 1.142 | 0.337 |
| 2023.zip | tblGrid_2023_04.csv | other | 1.105 | 0.325 |
| 2023.zip | tblGrid_2023_05.csv | other | 1.132 | 0.334 |
| 2023.zip | tblGrid_2023_06.csv | other | 1.086 | 0.32 |
| 2023.zip | tblGrid_2023_07.csv | other | 1.13 | 0.335 |
| 2023.zip | tblGrid_2023_08.csv | other | 1.137 | 0.336 |
| 2023.zip | tblGrid_2023_09.csv | other | 1.103 | 0.333 |
| 2023.zip | tblGrid_2023_10.csv | other | 1.141 | 0.344 |
| 2023.zip | tblGrid_2023_11.csv | other | 1.103 | 0.327 |
| 2023.zip | tblGrid_2023_12.csv | other | 1.145 | 0.342 |
| 2023.zip | tblSCTurbine_2023_01.csv | scada_10min | 142.8 | 33.8 |
| 2023.zip | tblSCTurbine_2023_02.csv | scada_10min | 128.1 | 29.88 |
| 2023.zip | tblSCTurbine_2023_03.csv | scada_10min | 143.6 | 33.56 |
| 2023.zip | tblSCTurbine_2023_04.csv | scada_10min | 139.1 | 32.49 |
| 2023.zip | tblSCTurbine_2023_05.csv | scada_10min | 142.6 | 33.05 |
| 2023.zip | tblSCTurbine_2023_06.csv | scada_10min | 137 | 31.74 |
| 2023.zip | tblSCTurbine_2023_07.csv | scada_10min | 143.7 | 33.4 |
| 2023.zip | tblSCTurbine_2023_08.csv | scada_10min | 143.2 | 33.28 |
| 2023.zip | tblSCTurbine_2023_09.csv | scada_10min | 139.6 | 32.99 |
| 2023.zip | tblSCTurbine_2023_10.csv | scada_10min | 143.5 | 34.03 |
| 2023.zip | tblSCTurbine_2023_11.csv | scada_10min | 136.4 | 31.77 |
| 2023.zip | tblSCTurbine_2023_12.csv | scada_10min | 139.6 | 33.14 |
| 2023.zip | tblSCTurCount_2023_01.csv | scada_10min | 70.95 | 9.982 |
| 2023.zip | tblSCTurCount_2023_02.csv | scada_10min | 65.43 | 8.666 |
| 2023.zip | tblSCTurCount_2023_03.csv | scada_10min | 73.2 | 9.984 |
| 2023.zip | tblSCTurCount_2023_04.csv | scada_10min | 72.12 | 9.774 |
| 2023.zip | tblSCTurCount_2023_05.csv | scada_10min | 73.05 | 9.781 |
| 2023.zip | tblSCTurCount_2023_06.csv | scada_10min | 70.47 | 9.35 |
| 2023.zip | tblSCTurCount_2023_07.csv | scada_10min | 74 | 9.93 |
| 2023.zip | tblSCTurCount_2023_08.csv | scada_10min | 73.42 | 9.82 |
| 2023.zip | tblSCTurCount_2023_09.csv | scada_10min | 70.16 | 9.689 |
| 2023.zip | tblSCTurCount_2023_10.csv | scada_10min | 74.29 | 10.54 |
| 2023.zip | tblSCTurCount_2023_11.csv | scada_10min | 69.37 | 9.327 |
| 2023.zip | tblSCTurCount_2023_12.csv | scada_10min | 70.38 | 9.619 |
| 2023.zip | tblSCTurDigiIn_2023_01.csv | scada_10min | 48.15 | 1.469 |
| 2023.zip | tblSCTurDigiIn_2023_02.csv | scada_10min | 43.82 | 1.307 |
| 2023.zip | tblSCTurDigiIn_2023_03.csv | scada_10min | 48.46 | 1.457 |
| 2023.zip | tblSCTurDigiIn_2023_04.csv | scada_10min | 46.94 | 1.41 |
| 2023.zip | tblSCTurDigiIn_2023_05.csv | scada_10min | 48.48 | 1.427 |
| 2023.zip | tblSCTurDigiIn_2023_06.csv | scada_10min | 46.33 | 1.348 |
| 2023.zip | tblSCTurDigiIn_2023_07.csv | scada_10min | 47.85 | 1.403 |
| 2023.zip | tblSCTurDigiIn_2023_08.csv | scada_10min | 48.34 | 1.406 |
| 2023.zip | tblSCTurDigiIn_2023_09.csv | scada_10min | 46.92 | 1.39 |
| 2023.zip | tblSCTurDigiIn_2023_10.csv | scada_10min | 48.55 | 1.474 |
| 2023.zip | tblSCTurDigiIn_2023_11.csv | scada_10min | 26.45 | 1.129 |
| 2023.zip | tblSCTurDigiIn_2023_12.csv | scada_10min | 27.3 | 1.179 |
| 2023.zip | tblSCTurDigiOut_2023_01.csv | scada_10min | 32.78 | 0.867 |
| 2023.zip | tblSCTurDigiOut_2023_02.csv | scada_10min | 29.78 | 0.817 |
| 2023.zip | tblSCTurDigiOut_2023_03.csv | scada_10min | 32.96 | 0.872 |
| 2023.zip | tblSCTurDigiOut_2023_04.csv | scada_10min | 31.94 | 0.88 |
| 2023.zip | tblSCTurDigiOut_2023_05.csv | scada_10min | 33.02 | 0.946 |
| 2023.zip | tblSCTurDigiOut_2023_06.csv | scada_10min | 31.56 | 0.887 |
| 2023.zip | tblSCTurDigiOut_2023_07.csv | scada_10min | 32.43 | 0.925 |
| 2023.zip | tblSCTurDigiOut_2023_08.csv | scada_10min | 32.94 | 0.923 |
| 2023.zip | tblSCTurDigiOut_2023_09.csv | scada_10min | 31.95 | 0.853 |
| 2023.zip | tblSCTurDigiOut_2023_10.csv | scada_10min | 33.04 | 0.874 |
| 2023.zip | tblSCTurDigiOut_2023_11.csv | scada_10min | 18.1 | 0.735 |
| 2023.zip | tblSCTurDigiOut_2023_12.csv | scada_10min | 18.67 | 0.745 |
| 2023.zip | tblSCTurFlag_2023_01.csv | scada_10min | 18.32 | 0.502 |
| 2023.zip | tblSCTurFlag_2023_02.csv | scada_10min | 16.58 | 0.477 |
| 2023.zip | tblSCTurFlag_2023_03.csv | scada_10min | 18.37 | 0.614 |
| 2023.zip | tblSCTurFlag_2023_04.csv | scada_10min | 17.76 | 0.576 |
| 2023.zip | tblSCTurFlag_2023_05.csv | scada_10min | 18.33 | 0.628 |
| 2023.zip | tblSCTurFlag_2023_06.csv | scada_10min | 17.49 | 0.601 |
| 2023.zip | tblSCTurFlag_2023_07.csv | scada_10min | 18.34 | 0.591 |
| 2023.zip | tblSCTurFlag_2023_08.csv | scada_10min | 18.3 | 0.622 |
| 2023.zip | tblSCTurFlag_2023_09.csv | scada_10min | 17.79 | 0.58 |
| 2023.zip | tblSCTurFlag_2023_10.csv | scada_10min | 18.44 | 0.534 |
| 2023.zip | tblSCTurFlag_2023_11.csv | scada_10min | 10.73 | 0.475 |
| 2023.zip | tblSCTurFlag_2023_12.csv | scada_10min | 11.11 | 0.466 |
| 2023.zip | tblSCTurGrid_2023_01.csv | scada_10min | 68.17 | 21.11 |
| 2023.zip | tblSCTurGrid_2023_02.csv | scada_10min | 61.62 | 19.01 |
| 2023.zip | tblSCTurGrid_2023_03.csv | scada_10min | 68.6 | 21.43 |
| 2023.zip | tblSCTurGrid_2023_04.csv | scada_10min | 66.39 | 20.72 |
| 2023.zip | tblSCTurGrid_2023_05.csv | scada_10min | 68.37 | 21.17 |
| 2023.zip | tblSCTurGrid_2023_06.csv | scada_10min | 65.22 | 20.33 |
| 2023.zip | tblSCTurGrid_2023_07.csv | scada_10min | 68.36 | 21.19 |
| 2023.zip | tblSCTurGrid_2023_08.csv | scada_10min | 68.11 | 21.09 |
| 2023.zip | tblSCTurGrid_2023_09.csv | scada_10min | 66.17 | 20.44 |
| 2023.zip | tblSCTurGrid_2023_10.csv | scada_10min | 68.53 | 20.99 |
| 2023.zip | tblSCTurGrid_2023_11.csv | scada_10min | 65.38 | 20.14 |
| 2023.zip | tblSCTurGrid_2023_12.csv | scada_10min | 67.26 | 20.46 |
| 2023.zip | tblSCTurIntern_2023_01.csv | scada_10min | 22.98 | 5.37 |
| 2023.zip | tblSCTurIntern_2023_02.csv | scada_10min | 20.73 | 4.863 |
| 2023.zip | tblSCTurIntern_2023_03.csv | scada_10min | 23.22 | 5.257 |
| 2023.zip | tblSCTurIntern_2023_04.csv | scada_10min | 22.53 | 5.138 |
| 2023.zip | tblSCTurIntern_2023_05.csv | scada_10min | 23.22 | 5.338 |
| 2023.zip | tblSCTurIntern_2023_06.csv | scada_10min | 22.26 | 5.06 |
| 2023.zip | tblSCTurIntern_2023_07.csv | scada_10min | 23.32 | 5.282 |
| 2023.zip | tblSCTurIntern_2023_08.csv | scada_10min | 23.28 | 5.298 |
| 2023.zip | tblSCTurIntern_2023_09.csv | scada_10min | 22.58 | 5.184 |
| 2023.zip | tblSCTurIntern_2023_10.csv | scada_10min | 23.2 | 5.348 |
| 2023.zip | tblSCTurIntern_2023_11.csv | scada_10min | 22.23 | 5.08 |
| 2023.zip | tblSCTurIntern_2023_12.csv | scada_10min | 22.73 | 5.316 |
| 2023.zip | tblSCTurPress_2023_01.csv | scada_10min | 55.03 | 15.33 |
| 2023.zip | tblSCTurPress_2023_02.csv | scada_10min | 49.41 | 13.78 |
| 2023.zip | tblSCTurPress_2023_03.csv | scada_10min | 54.52 | 15.11 |
| 2023.zip | tblSCTurPress_2023_04.csv | scada_10min | 53.05 | 15.04 |
| 2023.zip | tblSCTurPress_2023_05.csv | scada_10min | 54.66 | 15.62 |
| 2023.zip | tblSCTurPress_2023_06.csv | scada_10min | 52.14 | 14.74 |
| 2023.zip | tblSCTurPress_2023_07.csv | scada_10min | 54.91 | 15.49 |
| 2023.zip | tblSCTurPress_2023_08.csv | scada_10min | 54.67 | 15.47 |
| 2023.zip | tblSCTurPress_2023_09.csv | scada_10min | 53.01 | 15.06 |
| 2023.zip | tblSCTurPress_2023_10.csv | scada_10min | 54.68 | 15.44 |
| 2023.zip | tblSCTurPress_2023_11.csv | scada_10min | 52.42 | 14.55 |
| 2023.zip | tblSCTurPress_2023_12.csv | scada_10min | 54.2 | 14.89 |
| 2023.zip | tblSCTurTemp_2023_01.csv | scada_10min | 124.2 | 41.4 |
| 2023.zip | tblSCTurTemp_2023_02.csv | scada_10min | 109.5 | 35.38 |
| 2023.zip | tblSCTurTemp_2023_03.csv | scada_10min | 120.9 | 39.08 |
| 2023.zip | tblSCTurTemp_2023_04.csv | scada_10min | 118.8 | 38.79 |
| 2023.zip | tblSCTurTemp_2023_05.csv | scada_10min | 122.7 | 39.77 |
| 2023.zip | tblSCTurTemp_2023_06.csv | scada_10min | 116.4 | 37.26 |
| 2023.zip | tblSCTurTemp_2023_07.csv | scada_10min | 122 | 39.16 |
| 2023.zip | tblSCTurTemp_2023_08.csv | scada_10min | 121.9 | 39.04 |
| 2023.zip | tblSCTurTemp_2023_09.csv | scada_10min | 120.7 | 39.6 |
| 2023.zip | tblSCTurTemp_2023_10.csv | scada_10min | 124.1 | 40.78 |
| 2023.zip | tblSCTurTemp_2023_11.csv | scada_10min | 114.7 | 36.73 |
| 2023.zip | tblSCTurTemp_2023_12.csv | scada_10min | 119.7 | 38.87 |
| Hill_of_Towie_AeroUp_install_dates.csv | (loose file) | metadata | 0.001 | 0.001 |
| Hill_of_Towie_alarms_description.csv | (loose file) | metadata | 0 | 0 |
| Hill_of_Towie_grid_fields_description.csv | (loose file) | metadata | 0.001 | 0.001 |
| Hill_of_Towie_ShutdownDuration.zip | ShutdownDuration.csv | status_events | 316.8 | 19.83 |
| Hill_of_Towie_tables_description.csv | (loose file) | metadata | 0.001 | 0.001 |
| Hill_of_Towie_turbine_fields_description.csv | (loose file) | metadata | 0.004 | 0.004 |
| Hill_of_Towie_turbine_metadata.csv | (loose file) | metadata | 0.002 | 0.002 |
