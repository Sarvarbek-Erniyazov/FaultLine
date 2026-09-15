# PHMSA incident file: read-only inspection

| field | value |
| --- | --- |
| file | Hazardous Liquid Accident Data - January 2010 to present.zip |
| size (MB) | 4.6 |
| sha256 | 5aaa1a31834a0503acfdfc82172d9ff3483b480019cec1605ebb8e15d0040f0d |
| url | https://data.transportation.gov/api/views/27nc-rsge/files/1d547e17-2be1-4a32-9958-a1d5a946ade9?download=true&filename=Hazardous%20Liquid%20Accident%20Data%20-%20January%202010%20to%20present.zip |
| retrieval method | automated, robots.txt-gated client |
| retrieved (recorded) | 2026-09-15T20:49:12+00:00 |
| licence | public domain (17 U.S.C. 105); usa.gov public-domain label |


## Members, by pipeline type and form generation (best-effort, from filenames)

| member | classification (guessed) | encoding / delimiter | rows read | data lines | columns | narrative column(s) |
| --- | --- | --- | --- | --- | --- | --- |
| accident_hazardous_liquid_jan2010_present.txt | hazardous liquid / 2010-present form | cp1252 / tab | 5,850 | 5,850 | 648 | COMMODITY_DETAILS, BLEND_DETAILS, BIO_DIESEL_DETAILS, ACCIDENT_DETAILS, HOW_EXTINGUISHED_OTHER_DETAIL, UPSTREAM_OPRTNL_CNTRL_DETAIL, DOWNSTREAM_OPRTNL_CNTRL_DETAIL, INCIDENT_AREA_DETAILS, PIPE_SEAM_DETAILS, PIPE_COATING_DETAILS, WELD_DETAILS, DIFF_GIRTH_WELD_SEAM_DETAIL, DIFF_GIRTH_WELD_COATING_DETAIL, VALVE_MAINLINE_DETAILS, PUMP_TYPE_DETAILS, PUMP_SERVICE_TYPE_DETAILS, TANK_VESSEL_DETAILS, ITEM_INVOLVED_DETAILS, MATERIAL_DETAILS, RUPTURE_DETAILS, RELEASE_TYPE_DETAILS, EST_COST_OTHER_DETAILS, MOP_CFR_SECTION_DETAILS, INTERNAL_INSPECTION_DETAILS, INSPECT_COMP_DETAILS, INVESTIGATION_STATUS_DETAILS, INVEST_NO_SCHEDULE_IND_DETAILS, INVEST_OTHER_IND_DETAILS, CAUSE_DETAILS, VISUAL_EXAM_DETAILS, CORROSION_TYPE_DETAILS, STRAY_CURRENT_DETAILS, CORROSION_BASIS_DETAILS, OTHER_CP_SURVEY_DETAILS, INT_VISUAL_EXAM_DETAILS, INT_CORROSION_TYPE_DETAILS, INT_CORROSION_BASIS_DETAILS, CORROSION_LOCATION_DETAILS, NF_OTHER_DETAILS, NF_EXTREME_WEATHER_DETAILS, STATE_LAW_EXEMPT_DETAIL, DEPTH_OF_GRADE_DETAIL, OSF_OTHER_WEATHER_DETAILS, INTENTIONAL_DETAILS, OSF_OTHER_DETAILS, CITATION_OTHER_DETAIL, PROTECTION_OTHER_DETAIL, OTHER_ANALYSIS_DETAILS, OTHER_FACTOR_DETAILS, STRESS_DETAILS, OTHER_CONTROL_RELIEF_DETAILS, OTHER_PUMP_DETAILS, OTHER_STRIPPED_DETAILS, OTHER_NON_THREADED_DETAILS, FAILURE_DETAILS, EQ_ADDITIONAL_OTHER_DETAILS, OVERFLOW_OTHER_DETAILS, OPERATION_DETAILS, OPERATION_RELATED_DETAILS, MISC_DETAILS, INCIDENT_UNKNOWN_COMMENTS, NARRATIVE |

## Qualifying columns: which free-text test each passed, and its numbers

| member | column | test | non-null | mean chars | distinct ratio | tokens |
| --- | --- | --- | --- | --- | --- | --- |
| accident_hazardous_liquid_jan2010_present.txt | NARRATIVE | name | 5,820 | 953.0 | 1.000 | 894,467 |
| accident_hazardous_liquid_jan2010_present.txt | INVESTIGATION_STATUS_DETAILS | name | 3,678 | 95.6 | 0.772 | 57,591 |
| accident_hazardous_liquid_jan2010_present.txt | CAUSE_DETAILS | name | 5,850 | 35.7 | 0.007 | 25,456 |
| accident_hazardous_liquid_jan2010_present.txt | EQ_ADDITIONAL_OTHER_DETAILS | name | 1,310 | 36.1 | 0.810 | 7,612 |
| accident_hazardous_liquid_jan2010_present.txt | RELEASE_TYPE_DETAILS | name | 513 | 72.1 | 0.953 | 6,009 |
| accident_hazardous_liquid_jan2010_present.txt | EST_COST_OTHER_DETAILS | name | 832 | 37.6 | 0.861 | 4,683 |
| accident_hazardous_liquid_jan2010_present.txt | OPERATION_DETAILS | name | 179 | 129.3 | 0.994 | 3,687 |
| accident_hazardous_liquid_jan2010_present.txt | FAILURE_DETAILS | name | 322 | 55.5 | 0.907 | 2,947 |
| accident_hazardous_liquid_jan2010_present.txt | MATERIAL_DETAILS | name | 1,083 | 16.3 | 0.432 | 2,633 |
| accident_hazardous_liquid_jan2010_present.txt | OPERATION_RELATED_DETAILS | name | 146 | 90.7 | 0.993 | 2,084 |
| accident_hazardous_liquid_jan2010_present.txt | MISC_DETAILS | name | 85 | 138.8 | 1.000 | 1,972 |
| accident_hazardous_liquid_jan2010_present.txt | INVEST_OTHER_IND_DETAILS | name | 77 | 147.7 | 0.987 | 1,712 |
| accident_hazardous_liquid_jan2010_present.txt | ACCIDENT_DETAILS | name | 272 | 37.5 | 0.860 | 1,478 |
| accident_hazardous_liquid_jan2010_present.txt | INVEST_NO_SCHEDULE_IND_DETAILS | name | 61 | 151.7 | 0.934 | 1,458 |
| accident_hazardous_liquid_jan2010_present.txt | ITEM_INVOLVED_DETAILS | name | 429 | 19.6 | 0.751 | 1,319 |
| accident_hazardous_liquid_jan2010_present.txt | OTHER_FACTOR_DETAILS | name | 211 | 36.4 | 0.848 | 1,217 |
| accident_hazardous_liquid_jan2010_present.txt | NF_OTHER_DETAILS | name | 77 | 88.2 | 0.883 | 1,126 |
| accident_hazardous_liquid_jan2010_present.txt | UPSTREAM_OPRTNL_CNTRL_DETAIL | name | 106 | 63.7 | 0.962 | 1,113 |
| accident_hazardous_liquid_jan2010_present.txt | DOWNSTREAM_OPRTNL_CNTRL_DETAIL | name | 109 | 61.7 | 0.954 | 1,103 |
| accident_hazardous_liquid_jan2010_present.txt | INTERNAL_INSPECTION_DETAILS | name | 127 | 49.7 | 0.969 | 1,021 |
| accident_hazardous_liquid_jan2010_present.txt | CORROSION_LOCATION_DETAILS | name | 164 | 31.9 | 0.854 | 919 |
| accident_hazardous_liquid_jan2010_present.txt | OSF_OTHER_DETAILS | name | 36 | 140.7 | 1.000 | 820 |
| accident_hazardous_liquid_jan2010_present.txt | CORROSION_TYPE_DETAILS | name | 79 | 71.0 | 0.937 | 801 |
| accident_hazardous_liquid_jan2010_present.txt | INT_CORROSION_TYPE_DETAILS | name | 104 | 50.9 | 0.817 | 791 |
| accident_hazardous_liquid_jan2010_present.txt | COMMODITY_DETAILS | name | 486 | 11.1 | 0.251 | 776 |
| accident_hazardous_liquid_jan2010_present.txt | INT_CORROSION_BASIS_DETAILS | name | 83 | 55.3 | 0.964 | 715 |
| accident_hazardous_liquid_jan2010_present.txt | INCIDENT_AREA_DETAILS | name | 210 | 19.8 | 0.862 | 697 |
| accident_hazardous_liquid_jan2010_present.txt | NF_EXTREME_WEATHER_DETAILS | name | 56 | 55.2 | 0.946 | 485 |
| accident_hazardous_liquid_jan2010_present.txt | OTHER_NON_THREADED_DETAILS | name | 42 | 61.5 | 0.976 | 422 |
| accident_hazardous_liquid_jan2010_present.txt | INSPECT_COMP_DETAILS | name | 94 | 28.2 | 0.979 | 418 |
| accident_hazardous_liquid_jan2010_present.txt | OTHER_PUMP_DETAILS | name | 55 | 39.1 | 0.982 | 354 |
| accident_hazardous_liquid_jan2010_present.txt | OTHER_CONTROL_RELIEF_DETAILS | name | 47 | 44.2 | 0.979 | 339 |
| accident_hazardous_liquid_jan2010_present.txt | PIPE_COATING_DETAILS | name | 123 | 16.8 | 0.634 | 332 |
| accident_hazardous_liquid_jan2010_present.txt | OVERFLOW_OTHER_DETAILS | name | 27 | 64.4 | 0.963 | 270 |
| accident_hazardous_liquid_jan2010_present.txt | INT_VISUAL_EXAM_DETAILS | name | 31 | 48.8 | 0.903 | 234 |
| accident_hazardous_liquid_jan2010_present.txt | MOP_CFR_SECTION_DETAILS | name | 38 | 33.7 | 0.974 | 226 |
| accident_hazardous_liquid_jan2010_present.txt | OTHER_CP_SURVEY_DETAILS | name | 16 | 62.2 | 1.000 | 166 |
| accident_hazardous_liquid_jan2010_present.txt | CORROSION_BASIS_DETAILS | name | 26 | 43.2 | 0.962 | 161 |
| accident_hazardous_liquid_jan2010_present.txt | TANK_VESSEL_DETAILS | name | 54 | 18.0 | 0.889 | 158 |
| accident_hazardous_liquid_jan2010_present.txt | PIPE_SEAM_DETAILS | name | 90 | 10.8 | 0.256 | 151 |
| accident_hazardous_liquid_jan2010_present.txt | OTHER_STRIPPED_DETAILS | name | 25 | 36.8 | 0.960 | 149 |
| accident_hazardous_liquid_jan2010_present.txt | STRAY_CURRENT_DETAILS | name | 11 | 88.6 | 1.000 | 136 |
| accident_hazardous_liquid_jan2010_present.txt | VISUAL_EXAM_DETAILS | name | 21 | 43.3 | 0.952 | 131 |
| accident_hazardous_liquid_jan2010_present.txt | WELD_DETAILS | name | 30 | 22.4 | 0.967 | 111 |
| accident_hazardous_liquid_jan2010_present.txt | OTHER_ANALYSIS_DETAILS | name | 27 | 26.1 | 0.963 | 111 |
| accident_hazardous_liquid_jan2010_present.txt | RUPTURE_DETAILS | name | 14 | 42.1 | 1.000 | 96 |
| accident_hazardous_liquid_jan2010_present.txt | PUMP_SERVICE_TYPE_DETAILS | name | 32 | 15.9 | 0.750 | 78 |
| accident_hazardous_liquid_jan2010_present.txt | STRESS_DETAILS | name | 12 | 43.2 | 1.000 | 77 |
| accident_hazardous_liquid_jan2010_present.txt | HOW_EXTINGUISHED_OTHER_DETAIL | name | 7 | 37.0 | 1.000 | 38 |
| accident_hazardous_liquid_jan2010_present.txt | VALVE_MAINLINE_DETAILS | name | 14 | 15.4 | 1.000 | 35 |
| accident_hazardous_liquid_jan2010_present.txt | PUMP_TYPE_DETAILS | name | 6 | 15.5 | 1.000 | 14 |
| accident_hazardous_liquid_jan2010_present.txt | INCIDENT_UNKNOWN_COMMENTS | name | 1 | 63.0 | 1.000 | 11 |
| accident_hazardous_liquid_jan2010_present.txt | OSF_OTHER_WEATHER_DETAILS | name | 1 | 72.0 | 1.000 | 10 |
| accident_hazardous_liquid_jan2010_present.txt | DEPTH_OF_GRADE_DETAIL | name | 9 | 3.9 | 1.000 | 9 |
| accident_hazardous_liquid_jan2010_present.txt | PROTECTION_OTHER_DETAIL | name | 1 | 42.0 | 1.000 | 6 |
| accident_hazardous_liquid_jan2010_present.txt | BIO_DIESEL_DETAILS | name | 2 | 4.5 | 1.000 | 2 |
| accident_hazardous_liquid_jan2010_present.txt | CITATION_OTHER_DETAIL | name | 1 | 18.0 | 1.000 | 2 |
| accident_hazardous_liquid_jan2010_present.txt | DIFF_GIRTH_WELD_SEAM_DETAIL | name | 1 | 3.0 | 1.000 | 1 |
| accident_hazardous_liquid_jan2010_present.txt | BLEND_DETAILS | name | 0 | 0.0 | 0.000 | 0 |
| accident_hazardous_liquid_jan2010_present.txt | DIFF_GIRTH_WELD_COATING_DETAIL | name | 0 | 0.0 | 0.000 | 0 |
| accident_hazardous_liquid_jan2010_present.txt | STATE_LAW_EXEMPT_DETAIL | name | 0 | 0.0 | 0.000 | 0 |
| accident_hazardous_liquid_jan2010_present.txt | INTENTIONAL_DETAILS | name | 0 | 0.0 | 0.000 | 0 |

## Totals

| field | value |
| --- | --- |
| members read as tabular data | 1 |
| members with a narrative column found | 1 |
| total rows | 5,850 |
| total whitespace-token estimate, all narrative columns | 1,030,940 |

## Sampled narrative values, verbatim (truncated to 300 characters)

| member | sample |
| --- | --- |
| accident_hazardous_liquid_jan2010_present.txt | "AT APPROXIMATELY 15:05 ON 1-31-2026 OPERATOR CONDUCTING ROUTINE FACILITY ROUNDS DISCOVERED CRUDE OIL LEAKING FROM THE BODY OF A 2” DRAIN VALVE ON THE MINIMUM FLOW 733 RECIRCULATION LINE OF THE BOOSTER DELIVERY MANIFOLD.  OPERATOR IMMEDIATELY SHUT DOWN THE BOOSTER PUMP AND CLOSED VALVES ON THE SEGME |
| accident_hazardous_liquid_jan2010_present.txt | "AT APPROXIMATELY 8:54 AM ON JANUARY 29, 2026, AN ONSITE TECHNICIAN DISCOVERED A LEAKING VALVE DURING A ROUTINE FACILITY INSPECTION. THE AREA SUPERVISOR AND LOCAL OPERATIONS TEAM WERE NOTIFIED IMMEDIATELY.  THE RELEASE WAS MANAGED BY PLACING ABSORBENT PADS AROUND THE CONCRETE CONTAINMENT TO PREVENT  |
| accident_hazardous_liquid_jan2010_present.txt | "ON 1/28/2026 AT 12:36 PM CST, DURING NORMAL ACTIVITIES IN THE DIXIE SULPHUR STATION, A DIXIE PIPELINE TECHNICIAN DISCOVERED PROPANE VAPOR LEAKING FROM A MAIN LINE VALVE BONNET AND ACTUATOR ON THE DIXIE PIPELINE. THE SECTION OF PIPELINE WAS ISOLATED AND PURGED TO REPLACE THE MAINLINE VALVE. INSTALLA |
