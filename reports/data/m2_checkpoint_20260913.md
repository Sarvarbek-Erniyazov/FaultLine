# M2 checkpoint: corpus assembly and measurement

**Date:** 2026-09-13 · **Status:** Checkpoint per the user's 2026-09-13 instruction to
stop after corpus assembly and measurement. No BPE fit, no shards, no pretraining, no
dataset cards past this point until this report is reviewed.

Sources measured: the five staged `nrc.gov` collections (`nrc_event_notifications`,
`nrc_info_notices`, `nrc_bulletins`, `nrc_gen_letters`, `nrc_reg_issues`), assembled
into `data/raw/text/nrc_operator_narratives.jsonl` (33,725 documents) via
`faultline text corpus`. `status_code_book` (264 status strings, 938 whitespace
tokens) is staged separately and reported separately — it is a code book, not
narrative text, and is not pooled into the corpus figures below. PHMSA is not
staged (see (e)); its numbers are not in any total below.

Every count in this report is a fresh measurement against the files actually on
disk after the third and final `nrc_event_notifications` crawl (see (e) for why
three passes were needed). Token counts are whitespace-split word counts, not a
fitted tokenizer's count — acceptable at this stage per the M2 brief.

---

## (a) Per source and per HTML-template era

Event notifications is the only source that spans more than one HTML template; the
other four each use a single, unchanging document template throughout, so they get
one row each.

### Event notifications, by template era

Era is measured per document, not inferred from date: `extract_events()` tags every
document with whichever of the three extractors actually matched it. This caught two
genuine transition years where different *days* within the same year use different
templates (below) — a single day's page is never itself mixed.

| era | years (as measured) | report days fetched (≥1 event) | documents extracted | documents empty/<50 chars | whitespace tokens |
| --- | --- | --- | --- | --- | --- |
| legacy (`<pre>` box-drawn ASCII) | 1999–2003 | 1,116 | 6,263 | 2 | 1,359,413 |
| midera (`<a name="enNNNNN">` / table) | 2003–2020 | 4,175 | 22,523 | 3 | 5,724,541 |
| modern (USWDS `grid border`) | 2020–2026 | 1,509 | 3,669 | 0 | 861,033 |
| **total** | 1999–2026 | **6,800** | **32,455** | **5** | **7,944,987** |

Two years are genuine template transitions, not clean cutovers (confirmed no single
*day's* page mixes templates — the transition happens between different days within
the year):

- **2003**: 848 days' documents come back `legacy`, 500 come back `midera`.
- **2020**: 854 days' documents come back `midera`, 93 come back `modern`.

**6,948 report days were fetched in total** (the figure the crawl itself reports);
6,800 of them yielded at least one event and so carry an era tag. The remaining 148
days are genuine "no events reported" days (confirmed by the 224-day regression
sweep behind commit `1fa805f`) and carry no era tag, since no document exists to
derive one from — attributing them would need one more, separate small measurement
pass, not done here since it doesn't change any document count above.

The five empty/under-50-character documents are not extraction failures; each was
inspected directly:

| doc_id | era | full text |
| --- | --- | --- |
| `20010807en_en38188` | legacy | `NO REPORTED EVENTS TO RELEASE ON AUGUST 7, 2001` |
| `20011203en_en38527` | legacy | `.` |
| `20140328en_en49966` | midera | `FITNESS FOR DUTY VIOLATION` |
| `20141217en_en50687` | midera | `MAIN PLANT VENT RADIATION MONITOR UNAVAILABLE` |
| `20141217en_en50688` | midera | `AUTOMATIC REACTOR TRIP` |

The first is a placeholder for a day with nothing to report that nonetheless
carries an `EVENT TEXT` block; the second is a degenerate legacy-page artifact; the
last three are real events whose only published text is their own title — NRC did
not file a longer narrative for them within the report window. All five are
genuine, not a parsing defect: none contains a leaked HTML fragment or a truncation
marker.

### The four generic-communications sources (single template each)

| source | native HTML links found | documents extracted | documents empty/<50 chars | whitespace tokens |
| --- | --- | --- | --- | --- |
| Information Notices | 424 | 424 | 0 | 404,615 |
| Bulletins | 230 | 230 | 0 | 273,697 |
| Generic Letters | 563 | 563 | 0 | 747,952 |
| Regulatory Issue Summaries | 53 | 53 | 0 | 91,554 |

Every native-HTML link found yields exactly one document for these four sources —
already established in ADR-0016's corrected yield table, re-confirmed here against
the actually-staged files rather than re-asserted.

---

## (b) Ten sampled documents per template era, verbatim

Drawn with a fixed seed (`20260913`) from the non-degenerate documents (≥50
characters) of each era, sorted by `doc_id`. Shown exactly as staged, including the
source's own quotation marks, section headers and update-log conventions — nothing
trimmed except where noted.

### legacy

**`19990330en_en35522`** (<https://www.nrc.gov/reading-rm/doc-collections/event-status/event/1999/19990330en#en35522>)

```
AUTOMATIC TURBINE TRIP/REACTOR SCRAM DUE TO SPURIOUS HIGH VIBRATION SIGNAL

 The unit received an automatic turbine trip/reactor scram due to a suspected
 spurious turbine high vibration signal. Following the scram, all control
 rods inserted, and all systems functioned as expected. Two safety/relief
 valves lifted but immediately reseated. Primary Containment Isolation System
 (PCIS) Group 2 (drywell equipment and floor drains, TIP, radwaste, and
 process sampling), 6 (containment atmosphere and post-accident sampling),
 and 8 (RHR shutdown cooling) isolations occurred due to reactor vessel water
 level shrinkage following the scram. Reactor vessel water level recovered
 shortly after the scram.

 The licensee is currently investigating the cause of the turbine vibration
 signal. The NRC resident inspector has been informed of this event by the
 licensee.
```

**`19990607en_en35798`** (<https://www.nrc.gov/reading-rm/doc-collections/event-status/event/1999/19990607en#en35798>)

```
REACTOR BUILDING EMERGENCY COOLING SYSTEM OPERABLE BUT DEGRADED

 "At 1717 hours on June 4, 1999, GPU Nuclear determined that a condition that
 is outside the plant design basis may exist at TMI-1 due to potential
 degraded performance of the Reactor Building [RB] Emergency Cooling System.
 Measurements of indirect system performance parameters for the TMI-1 Reactor
 Building Emergency Cooling System indicate that the air flow through the
 system may be less than that assumed in the plant design basis.

 "Specifically, air flow in the RB Normal Cooling system, that utilizes duct
 work and a flow damper common to both the RB Normal cooling system and the
 RB Emergency Cooling System, has been found to be below previous air flow
 measurements. The air flow reduction may be indicative of a reduced air flow
 that would occur in the RB Emergency Cooling system if it was called upon to
 function in the event of a design basis accident. The design basis flow for
 the RB Emergency Cooling System is 25,000 CFM with the RB cooling fans in
 slow speed. Engineering judgement is that the current flow rate may be below
 25,000 CFM if the system was called upon to function, hence the
 identification of a condition outside the plant design basis.

 "Engineering judgement is that: the Reactor Building Emergency Cooling
 System remains operable but may be degraded. The judgement that the system
 is operable with degraded air flow is based on the difference between
 conservative assumptions in environmental temperatures in the plant design
 basis analysis and current environmental conditions and in view of the fact
 that the environmental conditions within the Reactor Building in the design
 basis accident should enhance the current potential degraded system air
 flow. A formal internal justification of continued operation (JCO) will be
 prepared to document the basis for the engineering judgement and will be
 provided to the site NRC resident inspectors office.

 "Because GPU Nuclear has classified this condition as being potentially
 outside the design basis of the plant, GPU Nuclear is notifying the NRC
 Operations Center in accordance with 10 CFR 50.72(b)(1)(ii)(b). This
 notification will be followed with a 30 day LER in accordance with 10 CFR
 50.73.

 "GPU Nuclear will document this condition in its 10 CFR 50 Appendix B
 corrective action program and this potential non-conformance is being
 addressed in accordance with the guidance provided in NRC Generic Letter
 91-18, Rev 1."

 The licensee notified the NRC Resident Inspector.
```

**`19991029en_en36367`** (<https://www.nrc.gov/reading-rm/doc-collections/event-status/event/1999/19991029en#en36367>)

```
MEDICAL MISADMINISTRATION

 A patient received a fractional dose to the wrong area because of problems
 with the measuring device used to locate the dose. The reference point used
 was 950 mm, but it should have been 995 mm. The error resulted from the
 measuring device "snagging" on a kink in the cable, thus preventing complete
 insertion. The net result was an error of approximately 4.5 cm. The 380
 cGy fraction was delivered to the end of the nose vice further in as
 prescribed. The fraction was one of four planned with a total intended dose
 of 1520 cGy. The source involved was 6.8 Ci of Ir-192.

 The patient and doctor have been informed of the error. No adverse
 consequences are expected for the patient.
```

**`20000126en_en36627`** (<https://www.nrc.gov/reading-rm/doc-collections/event-status/event/2000/20000126en#en36627>)

```
10 CFR 21 - POTENTIAL DEFECT INVOLVING STATIC SWITCH CONTROL ASSEMBLY AND
 REGULATED RECTIFIER CONTROL ASSEMBLY USED IN AN UNINTERRUPTIBLE POWER
 SYSTEM

 This reports a potential for a defect in Static Switch Control assemblies
 and Regulated Rectifier Control assemblies used in Uninterruptible Power
 Systems manufactured under the Solidstate Controls, Inc., 10CFR50 Appendix B
 Program.

 Each of the plants has been notified of this report and requested to return
 the affected assemblies for replacement. The following plants have affected
 components: Indian Point 2, Catawba, Oconee, Arkansas Nuclear One,
 Waterford 3, Crystal River, Diablo Canyon, Sequoyah, and Surry.

 The problem is associated with a component part - Unijunction Transistor,
 part number 03-650007-00, that has been found to sometimes cause random,
 sporadic transfers of the static switch due to a higher level of sensitivity
 to noise spikes on the input line or cause the regulated rectifier to output
 a higher DC voltage. This increase in sensitivity will not cause the system
 to drop power to the load, if the alternate source is not available the
 static switch will not transfer, continuing to protect the load.
```

**`20000822en_en37208`** (<https://www.nrc.gov/reading-rm/doc-collections/event-status/event/2000/20000822en#en37208>)

```
DISCOVERY OF A MINIMAL AMOUNT OF WATER IN THE REACTOR CORE ISOLATION COOLING
 OIL SYSTEM

 The following text is a portion of a facsimile received from the licensee:

 "EVENT: The Unit 2 the Reactor Core Isolation Cooling (RCIC) system was
 discovered to have a minimal amount of water in the oil system. Following
 investigation of the event and replacement of the oil, the RCIC turbine was
 successfully manually started and operated normally. During a subsequent
 automatic start for post-maintenance test requirements, the turbine tripped
 on high exhaust pressure apparently caused by the governor system's slow
 response time. Investigation of the turbine control system is continuing."

 "CORRECTIVE ACTION(S): Continue the investigation to determine the root
 cause of the water in the oil system and the response of the governor
 control system."

 "INITIAL SAFETY SIGNIFICANCE EVALUATION: Minimal. The High Pressure
 Coolant Injection System, Automatic [Depressurization] System, Low Pressure
 Core Spray, and the Low Pressure Coolant Injection System were operable
 throughout the event."

 The licensee stated that, as a result of this issue, the unit is currently
 in a 14-day limiting condition for operation in accordance with Technical
 Specification 3.5.2. The licensee also stated that all other systems
 functioned as required.

 The licensee notified the NRC resident inspector.

 * * * UPDATE ON 8/21/00 @ 1050 BY ELBERFELD TO GOULD * * * RETRACTION

 Upon further investigation, it has been determined that the condition
 resulting in the RCIC turbine trip developed during the period of time that
 the system was inoperable for maintenance, and that there was no loss of
 safety function.

 After the notification was made it was determined that the trip of the RCIC
 turbine was caused by the presence of air in the control system for the
 governor valve positioning servo. The presence of air delayed the closing of
 the governor valve during the RCIC turbine start sequence, allowing the
 turbine speed to increase, thus increasing turbine exhaust pressure above
 the trip setpoint. The presence of air was introduced by the maintenance
 activities associated with changing the turbine lube oil. An acknowledged
 industry expert was consulted and confirmed that one controlled manual start
 would not be considered adequate to remove air from the governor control
 system even with a substantial run duration. Experience has shown that
 multiple starts, at least 2 to 3 governor valve strokes, may be needed to
 remove the air that can cause abnormal turbine starts.

 Review of the "as found" condition of the RCIC system and the RCIC system
 performance before and after the turbine trip indicates that the RCIC system
 would have successfully performed its intended functions prior to being
 taken out of service for maintenance on August 4, 2000. This is based on
 the following.

 * The system quick started and ran successfully on August 2, 2000, prior to
 the oil sample being taken that contained the water.
 * The presence of water in the lube oil did not cause the turbine trip and
 did not have an adverse impact on short-term system operability.
 * Both turbine trips during the quick-starts were the result of minimal
 governor valve stroking after the lube oil changes introduced air into the
 governor valve control system.
 * The RCIC turbine was able to achieve a quick-start without tripping,
 during the performance of OPT-10.1.1 on August 7, 2000, after the governor
 valve had been stroked twice (i.e., the controlled manual start and a failed
 quick-start).

 This event is being retracted by the licensee.

 The NRC Resident Inspector was notified by the licensee. The R2DO (Paul
 Fredrickson) was notified by the NRC Operations Officer.
```

**`20001024en_en37450`** (<https://www.nrc.gov/reading-rm/doc-collections/event-status/event/2000/20001024en#en37450>)

```
THE LICENSEE MADE NOTIFICATION TO FLORIDA FISH AND WILDLIFE CONSERVATION
 COMMISSION

 This notification was made due to a live loggerhead turtle being found in
 the intake net. The turtle was not in very good condition. It will be sent
 off site for rehabilitation.

 The NRC Resident Inspector was notified.
```

**`20001108en_en37500`** (<https://www.nrc.gov/reading-rm/doc-collections/event-status/event/2000/20001108en#en37500>)

```
POSITIVE FOR-CAUSE TEST FOR ALCOHOL REPORTED IN ACCORDANCE WITH 10 CFR
 26.73.a(2)(ii)

 A contract supervisor was determined to be under the influence of alcohol
 during a for-cause test. The individual's site access was suspended, and
 the individual was subsequently terminated. (Contact the NRC operations
 officer for addition details.)

 The licensee notified the NRC resident inspector and plans to notify the NRC
 Region 3 office.
```

**`20001116en_en37524`** (<https://www.nrc.gov/reading-rm/doc-collections/event-status/event/2000/20001116en#en37524>)

```
MANUAL REACTOR TRIP DUE TO FAILURE OF TURBINE RUNBACK ACTUATION CIRCUITS

 Unit 2 experienced a turbine runback at 1410 EST. The control room
 operators noticed all status lights for overpower and overtemperature delta
 T runback were illuminated. The operators decided to manually trip the
 reactor from about 23 % rated thermal power. The reactor trip resulted in a
 turbine trip as expected. Auxiliary feedwater pumps started due to low-low
 steam generator levels. The unit is stable in Mode 3.

 The runback bistables are locked in without having the logic bistables
 tripped that feed the trip circuit. The licensee is troubleshooting the
 problem and the cause is unknown at this time. The plant will remain in
 Mode 3 until the problem is corrected.

 The licensee notified the NRC Resident Inspector.
```

**`20010312en_en37818`** (<https://www.nrc.gov/reading-rm/doc-collections/event-status/event/2001/20010312en#en37818>)

```
MISSING LOW ACTIVITY SOURCE

 "During a routine inventory of licensed radioactive sources, one low
 activity, mixed isotope source could not be accounted for. The source
 contained a total of approximately 0.992 microcurie, of which approximately
 0.154 microcurie was americium-241. Since the quantity of americium-241 in
 this source was more than ten times greater than the quantity specified in
 Appendix C of 10CFR20, a telephone report is required in accordance with
 10CFR20.2201(a)(1)(ii). None of the other isotopes in the source exceeded
 reportable quantities specified in Appendix C. The low activity and
 relatively large physical size of the source are such that it would not be a
 significant radiological hazard. A search of the site failed to locate the
 source. It is not likely that a person could have inadvertently carried the
 source out of the radiologically controlled area (RCA) on his body since the
 source would have caused the RCA exit monitors to alarm. We have concluded
 that the source was most likely discarded by mistake inside the RCA into a
 yellow trash bag with other radioactive waste. The low level radioactive
 waste from the time period in question was shipped off site to a licensed
 vendor and has been incinerated."

 The NRC resident inspector has been informed of this event by the licensee.
```

**`20021009en_en39258`** (<https://www.nrc.gov/reading-rm/doc-collections/event-status/event/2002/20021009en#en39258>)

```
DEGRADATION OF RCS PRESSURE BOUNDARY AT ARKANSAS NUCLEAR ONE UNIT 1

 "With the Reactor Coolant System (RCS) In Mode 3 (Hot Standby) conditions at
 the start of a scheduled refueling outage on October 5, 2002, a leaking weld
 was discovered at the connection of a drain line to a High Pressure
 Injection (HPI) line inside the Reactor Building. The leak rate was
 approximately 0.2 gpm. The immediate evaluation concluded that this leak did
 not result in the HPI System being inoperable. Subsequent evaluation of the
 condition on October 8, 2002. determined that the leak was from the RCS
 pressure boundary. Between the RCS and leak location are a normally open
 manual isolation valve and a check valve. Weld repair is complete. This
 condition is being reported as a serious degradation of a principal safety
 barrier in accordance with 10CFR5O.72(b)(3)(ii)(A)."

 The licensee notified the NRC Resident Inspector.
```

### midera

**`20050217en_en41409`** (<https://www.nrc.gov/reading-rm/doc-collections/event-status/event/2005/20050217en#en41409>)

```
GEORGIA AGREEMENT STATE REPORT - MISSING RADIOACTIVE SOURCE
The following information was received from the State via facsimile:
"Description of Event: On December 27, 2004, Shaw Industries, a general licensee, contracted with Graves & Phillips Engineering & Maintenance (Alabama License Number 1291) to have four sources removed and returned to the supplier, Omhart. Upon arrival at Omhart on February 4, 2005, the package contained only three sources and one detector. Shaw Industries reported that the fourth source was possibly left on the line where it was used to measure thickness of carpet and that line was sent to a scrap metal yard on January 11, 2005. However, it is still undetermined what has happened to the missing source.
"The Environmental Radiation Staff and representatives from Shaw Industries have been dispatched to the scrap metal yard to investigate the incident. The source holder was Omhart Vega Model BAL and serial number 3781 BC. Isotope: Sr-90. Amount of activity: 25 milliCuries."
Georgia Event Report ID GA-05-05.
* * * UPDATE FROM C. SANDERS TO J. ROTTON AT 1549 ON 02/15/05 * * *
2 personnel from the Georgia Environmental Radiation Staff, 5 representatives from Shaw Industries, and 5 representatives from Regional Recycle are scheduled to physically dismantle the trash pile on 02/16/05 where the missing source is believed to be located and conduct a thorough search for the source. The pile is approximately 40' high, 35 yards wide, and 85 yards long.
Notified R1DO (Cobey) and NMSS EO (Moore).
* * * UPDATE FROM L. SEALE TO J. KNOKE AT 11:18 ON 02/16/05 * * *
"February 14, 2005
The Radioactive Materials Program notified the NRC Operations Center of the event. Attempts to find the source by Shaw Industries' representatives and Environmental Radiation Staff were unsuccessful. The scrap pile that may contain the source is approximately 75-100 yards long, 30-40 yards wide, and 40' to 50' high. Regional Recycling stated that there was a 99% chance that the material was destined for the steel mill across the street from their facility, that is, a 1% chance that the material would be sent to a scrap yard in Kentucky.
"February 15, 2005
Environmental Radiation Staff notified the state of Alabama of the event and ongoing investigation due to Graves & Phillips Engineering & Maintenance, an Alabama licensee. Shaw Industries forwarded to the Environmental Radiation Program dose profiles and pictures of the source device received from Ohmart. Regional Recycling reviewed its records and no shipments had been sent to the Kentucky facility since November 2004. All facilities were notified of the event and pictures and descriptions of the device were sent to the facilities that may receive scrap metal from Shaw Industries.
"Shaw Industries and the Radiation Program were informed by Regional Recycling (scrap yard) that they wanted to dismantle the scrap pile to try to locate the source. Shaw Industries, Regional Recycling and the Environmental Program will provide staff to facilitate the search. The search is to begin on February 16, 2005. Regional Recycling has halted their operations until the search is completed. The Radioactive Materials Program updated the NRC Operation Center on the status of the event.
"February 16, 2005
Shaw Industries and the Environmental Program are currently at Regional Recycling and are visually inspecting the scrap as it is sorted by a crane. The Radioactive Materials Program updated the NRC Operation Center on the status of the event."
Notified R1DO (Cobey) and NMSS EO (Essig).
```

**`20070220en_en43172`** (<https://www.nrc.gov/reading-rm/doc-collections/event-status/event/2007/20070220en#en43172>)

```
DEGRADED CONDITION - 30% THROUGH WALL INDICATION ON REACTOR RECIRC NOZZLE
 "Information from a Phased Array UT examination of RRF-17002 (Reactor Recirc 'F' Nozzle to Safe-end weld) indicates that a linear indication approximately 7" long (centered at the bottom of the weld) and approximately 30% through wall extent (ID connected) exists. The Phased Array UT examination of RRF-17002 (Reactor Recirc 'F' Nozzle to Safe-end weld) was performed as part of scheduled outage activities.
 "TRM LCO 3.7.3 for Structural Integrity, Condition B has been entered for the Recirc nozzle/piping.
 "This event is reportable under § 50.72(b)(3)(ii), 'Any event or condition that results in: (A) The condition of the nuclear power plant, including its principal safety barriers, being seriously degraded', when there are welding or material defects in the primary coolant system which cannot be found acceptable under ASME Section XI, IWB-3600, 'Analytical Evaluation of Flaws' or ASME Section XI, Table IWB-3410-1, 'Acceptance Standards.'"
 The licensee informed the NRC Resident Inspector.
```

**`20070427en_en43322`** (<https://www.nrc.gov/reading-rm/doc-collections/event-status/event/2007/20070427en#en43322>)

```
DEGRADED CONDITION DURING WELD DEPOSIT OVERLAY REPAIR
"On April 26, 2007, at approximately 1930 it was reported that the N2K recirculation system inlet nozzle had slight water seepage. The seepage developed during welding operations being performed to install a full structural weld overlay over the nozzle and stopped almost immediately during the welding. The weld overlay was being installed as a conservative measure following UT inspections that had been performed earlier during the outage.
This event is being reported in accordance with 10 CFR 50.72(b)(3)(ii)A. The plant is in stable condition."
The licensee notified the NRC Resident Inspector.
```

**`20071217en_en43838`** (<https://www.nrc.gov/reading-rm/doc-collections/event-status/event/2007/20071217en#en43838>)

```
FLORIDA AGREEMENT STATE REPORT
"A misadministration occurred on 11-Dec-2007 this office notified at 1520 hours. The prostate was to receive 140 Gy, but received only 100 Gy. This incident referred to Radioactive Materials for Investigation. This office will take no further action on this incident."
Isotope: I-125
Activity: 92 seeds at 0.295 millicuries per seed
Material Form: Interstitial Brachytherapy Seeds
Incident Number: FL07-193
A "Medical Event" may indicate potential problems in a medical facility's use of radioactive materials. It does not necessarily result in harm to the patient.
* * *UPDATE BY FSME (FLANNERY) TO MACKINNON AT 1105 ON 12/13/07* * *
"This event (EN43838) has been reviewed and determined to be a reportable medical event."
```

**`20090116en_en44756`** (<https://www.nrc.gov/reading-rm/doc-collections/event-status/event/2009/20090116en#en44756>)

```
AGREEMENT STATE REPORT - LOST TRITIUM EXIT SIGNS
The State of Minnesota was notified by a Wal-Mart corporate representative located in Bentonville, AR, indicating that Wal-Mart was unable to account for 319 tritium exit signs (which are general licensed materials) that were used at one time in Wal-Mart stores throughout the State of Minnesota. The Wal-Mart representative informed the State Office that Wal-Mart had exhausted searching for the tritium exit signs and considered them to be lost and/or missing. The State of Minnesota was provided a listing from corporate Wal-Mart of the store locations along with information on the tritium exit sign manufacturers, model and serial numbers and curie content where known.
THIS MATERIAL EVENT CONTAINS A "LESS THAN CAT 3" LEVEL OF RADIOACTIVE MATERIAL
Sources that are "Less than IAEA Category 3 sources," are either sources that are very unlikely to cause permanent injury to individuals or contain a very small amount of radioactive material that would not cause any permanent injury. Some of these sources, such as moisture density gauges or thickness gauges that are Category 4, the amount of unshielded radioactive material, if not safely managed or securely protected, could possibly - although it is unlikely - temporarily injure someone who handled it or were otherwise in contact with it, or who were close to it for a period of many weeks.
This source is not amongst those sources or devices identified by the IAEA Code of Conduct for the Safety & Security of Radioactive Sources to be of concern from a radiological standpoint. Therefore is it being categorized as a less than Category 3 source.
```

**`20130326en_en48850`** (<https://www.nrc.gov/reading-rm/doc-collections/event-status/event/2013/20130326en#en48850>)

```
PART 21 REPORT - FOREIGN MATERIAL INSIDE EDG AIR START PIPING
Facility Affected:
Xcel Energy - Prairie Island Nuclear Generating Plant (PINGP).
Component Affected:
OP Engine- Air Start Piping Assemble (p/n 11879060*00) shipped after October 23, 2012.
Supplier:
Fairbanks Morse Engine, 701 White Ave., Beloit, WI 53511.
Nature of Defect:
During a routine emergency diesel generator (EDG) test on 1/28/2013, one of the two redundant air start systems was isolated from the other and the single air start system failed to start the EDG due to the foreign material in the solenoid valve. The foreign material removed from the solenoid valve during failure analysis appears to be liquid pipe sealant used to seal threaded pipe joints during assembly.
Safety Hazard Which Could Be Created By Such Defect:
Foreign material within both of the redundant air start piping systems could become lodged in both of the solenoid valves. Simultaneous failure of the two solenoid valves would prevent the emergency diesel generator from starting.
Corrective Action:
PINGP has completed disassembly and cleaning of both piping systems to ensure no foreign material remains within the piping system.
FM will create a workmanship standard for pipe sealing, hydrostatic testing, and pressure testing that will include a foreign material exclusion program to ensure cleanliness of assemblies. This will be completed by June 30, 2013. FM has issued Corrective Action No. 2609 in its Quality Assurance Program.
```

**`20130520en_en48864`** (<https://www.nrc.gov/reading-rm/doc-collections/event-status/event/2013/20130520en#en48864>)

```
AGREEMENT STATE REPORT - UNDER DOSE IN BRACHYTHERAPY TREATMENT DUE TO USE OF WRONG LENGTH GUIDE WIRE
The following information was provided by the State of Texas via email:
"On March 28, 2013, the Agency [Texas Department of Health] was notified by the licensee that a medical event occurred on March 27, 2013. The licensee stated that the wrong length guide wire was used during 3 of 4 HDR [High-Dose Rate Brachytherapy] treatments. The error was discovered after the third treatment. The Radiation Safety Officer (RSO) stated the desired area of treatment was under dosed by more than 50 percent. The treatment plan prescribed 2400 cGy over 4 treatments. He stated that the patient and their physician were notified as soon as the error was discovered. The RSO is not at the facility and is trying to gather the information on the event over his phone. The licensee has suspended all HDR treatments until their process and procedures have been reviewed. Additional information will be provided as it is received in accordance with SA - 300.
"Texas Incident #: I-9059"
* * * UPDATE ON 4/11/13 AT 2126 EDT FROM ART TUCKER TO DONG PARK * * *
The following information was provided by the State of Texas via email:
"On April, 9, 2013, the licensee provided the following information: The Physicist of record retrieved tube connectors from the HDR supplies on shelves in the dosimetry area. The tube/connectors were stored, coiled in Ziploc bags. The Physicist selected green tubes when he saw the black tubes used previously were not on the shelf. He was unaware that there were two sets, each a different length when he selected the green set. The black tubes measure 120cm in length and the green tubes measure 132cm. The Senior Physicist, who was on vacation during the first two out of the four treatments, stored the black tube set in a drawer across the room. Physicist selected tubes which attached to the patient's treatment device. The Physicist planned the patient's treatment with the treatment lengths (119.9 cm) stated in our facility's HDR tandem and ring treatment planning procedure and forms but used the 132cm tube for the treatment delivery for three out of four fractions. Only the black tubes were used historically in tandem and ring HDR procedures and since their given length were known, they were not measured at the time of treatment delivery. The green tubes were also not measured prior to treatment delivery. The Physician of record saw the green tubes and believed their use was intentional. This medical event meant the patient's tissue to be treated (cervix) received less total radiation dose than that prescribed: 1,390 cGy (mean dose delivered) vs. the 5,139 cGy the cervix would have received over the four treatments. This is more than a 50 cGy (50 rem) effective dose equivalent difference to the cervix. In addition, the mean total dose delivered to the cervix over the four treatments differed from the prescribed dose by more than 20% (42.1% is the actual variance) and the delivered dose for at least one of the fractions differed by more than 50% from the prescribed dose (fraction #1 cervix mean dose delivered was 42.5 cGy vs. the 1,192.4 cGy expected) (fraction #2 cervix mean dose delivered was 34.6 cGy vs. the 1,416.3 cGy expected) and (fraction #3 cervix mean dose delivered was 45.2 cGy vs. the 1,262.2 cGy expected). The patient's urethra received a mean dose of 1,607 cGy for the four fractions. The maximum dose to 1 cc of the urethra for the four fractions was 1,849 cGy. The patient's anterior vagina received a mean dose from the four fractions of 1,549 cGy. The maximum dose to 1 cc of the anterior vagina for the four fractions was 3,049 cGy. The Agency [Texas Department of Health] has requested additional information from the licensee. Additional information will be provided in accordance with SA 300."
Notified R4DO (Deese) and FSME Events Resource via email.
* * * UPDATE AT 1107 EDT ON 5/17/2013 FROM ART TUCKER TO MARK ABRAMOVITZ * * *
The reference to a guide "wire" in the initial report was incorrect. An incorrect guide "tube" was used. Additionally, the title should have stated "GUIDE TUBE."
Notified the R4DO (Walker).
A Medical Event may indicate potential problems in a medical facility's use of radioactive materials. It does not necessarily result in harm to the patient.
```

**`20150403en_en50949`** (<https://www.nrc.gov/reading-rm/doc-collections/event-status/event/2015/20150403en#en50949>)

```
MANUAL REACTOR SCRAM DUE TO STEAM LEAK
"On April 2, 2015 at 2133 CDT, a manual scram was inserted on Unit 1 following discovery of a steam leak in the Turbine Building at the D-ring, near the Turbine Bypass valves. Following the reactor scram, reactor water level decreased to approximately -2 inches, which resulted in an automatic Group II and Group III isolation (expected response). The steam leak was isolated by manual closure of the Main Steam Isolation Valves. All systems responded properly to the event. Unit 1 remains in Mode 3, with cooldown in progress. Reactor water level is in the normal level band. The cause and details of the event are under investigation. Unit 2 was unaffected by the event and remains at 100 percent power."
Operators reduced reactor power to 20 percent before initiating a SCRAM. All rods fully inserted and the reactor is shutdown and stable. The electrical supply is in a normal shutdown lineup. The reactor is being supplied by normal feedwater, and decay heat is being controlled by use of the ADS valves. The licensee is currently cooling down and depressurizing the reactor in preparation for repair of the steam leak.
The licensee has notified the NRC Resident Inspector and the State of Illinois Resident Inspector.
```

**`20150511en_en51032`** (<https://www.nrc.gov/reading-rm/doc-collections/event-status/event/2015/20150511en#en51032>)

```
AGREEMENT STATE REPORT - IODINE 125 SEED LEFT IN PATIENT
 The following was received from the State of North Carolina via email:
 "During a recent facility inspection at Duke University Medical Center (License# 0247-4), it was discovered that a lost I-125 seed (National NMED Item #140177) was actually found a couple months later still in the patient's breast tissue. The seed was intended for radioactive seed localization (RSL) of a breast lesion and thought to be excised with the targeted tissue during surgery.
 "Events as follows:
 -Seed was implanted to patient with 213 uCi on 1/23/2014.
 -Discovered missing by licensee on 2/27/2014.
 -Reported lost to NC on 3/21/2014.
 -Found in patient 3/30/2014, no update given to NC.
 -Removed from patient breast on 4/1/2014.
 "As of 5/1/2015, the licensee maintains that there was only 12.5 rads received to the 250g of breast tissue and not above the 50 rem for medical event reporting. This is currently under investigation by the NC Radioactive Materials Branch as our preliminary numbers suggest the breast tissue dose could be as high as 66 rem in the maximally exposed 100g of tissue.
 "The licensee is not concerned with overall adverse reaction to the patient health due to them receiving a subsequent external beam radiation treatment that deposited between 300-1100 rads to the affected breast.
 "This possible medical event is tied to the former local NMED Incident# NC 140014 where the source was lost, and it is now being tracked by a new local NMED Incident# NC 150010."
 A Medical Event may indicate potential problems in a medical facility's use of radioactive materials. It does not necessarily result in harm to the patient.
```

**`20160525en_en51954`** (<https://www.nrc.gov/reading-rm/doc-collections/event-status/event/2016/20160525en#en51954>)

```
OFFSITE NOTIFICATION DUE TO ONSITE FATALITY NOT RELATED TO WORK
"At approximately 1250 [EDT], a contract employee was found unresponsive in [their] personal vehicle located in the parking lot outside of the owner controlled area. The Fairfield County Coroner arrived on-site and declared the individual deceased at 1345. The fatality was due to an apparent personal medical issue and not work related."
The licensee has notified the NRC Resident Inspector.
The licensee has notified State of South Carolina Department of Labor - OSHA.
```

### modern

**`20210615en_en55308`** (<https://www.nrc.gov/documents-reports/document-collections/events-reports-associated-with/event-notification-reports/2021/20210615en#en55308>)

```
EN Revision Imported Date: 7/15/2021
EN Revision Text: NON-AGREEMENT STATE - LOST MOISTURE DENSITY GAUGE
The following was received from the licensee via email:
"On Monday afternoon June 14, 2021, [the licensee] went to perform a leak test on Troxler gauge 70894 (Model No. 3430; Cs-137 8 milliCurie; Am-241/Be 40 milliCurie), which was due for a leak test the same date 6/14/21. [The licensee] looked in [their] system to see which employee had the gauge. It was not checked out by anyone that day so [the licensee] went through the storage room in Ann Arbor and then Troy to find the gauge and perform the test. The gauge was not present in either location. [The licensee] began making phone calls to employees to see if an employee had the gauge and it was just not checked out properly in [their] system.
"[The licensee] reviewed [their] system and determined the gauge was last used by a former employee on January 5, 2021. [The licensee] was able to reach that person and he indicated he returned the gauge to the locked storage room in [the] Ann Arbor office on January 6, 2021. The gauge was not shown as having been used by any employee since that date within [the] system. [The licensee does] not know when the gauge went missing or how the gauge was removed from the office. [The licensee] also cannot confirm if the former employee actually returned the gauge on January 6, 2021. Calibration and leak tests were performed in December 2020 by ATSNUC, Inc. [The licensee] contacted all of the service facilities that [they] use to see if it might be in for service but [the licensee has] been unable to locate the gauge. [The licensee is] also checking with all service centers listed on the APNGA website to see if by chance some other party has sent in/returned this gauge to one of those facilities. It was determined today, 6/15/21, at approximately 1534 EDT (less than 24 hours after the initial discovery) that [the licensee] could not locate the gauge."
The licensee notified the NRC Region III Office.
THIS MATERIAL EVENT CONTAINS A 'Less than Cat 3' LEVEL OF RADIOACTIVE MATERIAL
Sources that are "Less than IAEA Category 3 sources," are either sources that are very unlikely to cause permanent injury to individuals or contain a very small amount of radioactive material that would not cause any permanent injury. Some of these sources, such as moisture density gauges or thickness gauges that are Category 4, the amount of unshielded radioactive material, if not safely managed or securely protected, could possibly - although it is unlikely - temporarily injure someone who handled it or were otherwise in contact with it, or who were close to it for a period of many weeks. For additional information go to http://www-pub.iaea.org/MTCD/publications/PDF/Pub1227_web.pdf
```

**`20210913en_en55458`** (<https://www.nrc.gov/documents-reports/document-collections/events-reports-associated-with/event-notification-reports/2021/20210913en#en55458>)

```
EN Revision Imported Date: 10/13/2021
EN Revision Text: SPECIFIED SYSTEM ACTUATION
"At 0011 EDT, with Unit 2 in Mode 5 (Cold Shutdown), actuations of the 2B Diesel Generator (DG) and the 2B Motor Driven Auxiliary Feedwater (AFW) Pump occurred during Engineered Safety Features Actuation Periodic Testing while resetting the 2B DG Load Sequencer. The 2B DG was running unloaded following test actuation, and during realignment from the test, a blackout condition was experienced when the breaker opened supplying the 4160 Volt Essential Power System 2ETB from the Standby Auxiliary Power Transformer SATB. Sequencer actuation closed the emergency breaker to 2ETB and loaded the 2B Motor Driven AFW Pump onto the bus. Steam supply valves to the Turbine Driven AFW Pump were open from the previous test configuration.
"This event is being reported in accordance with 10CFR 50.72(b)(3)(iv)(A) as an event that results in a valid actuation of the 2B DG and the 2B Motor Driven AFW Pump.
"There was no impact on the health and safety of the public or plant personnel. The NRC Resident Inspector has been notified."
```

**`20220819en_en56060`** (<https://www.nrc.gov/documents-reports/document-collections/events-reports-associated-with/event-notification-reports/2022/20220819en#en56060>)

```
ALCOHOL DISCOVERED WITHIN THE PROTECTED AREA
A non-licensed, non-supervisory employee had a confirmed positive for alcohol during a for-cause fitness-for-duty test. Subsequent investigation revealed the presence of alcohol within the Protected Area. The employee's access to the plant has been terminated.
```

**`20221230en_en56290`** (<https://www.nrc.gov/documents-reports/document-collections/events-reports-associated-with/event-notification-reports/2022/20221230en#en56290>)

```
AGREEMENT STATE REPORT - LOST EXIT SIGNS
The following information was provided by Kansas Radiation Control Program via email:
"Kansas Radiation Control Program was notified, at 1016 CST on December 30, 2022, that six tritium exit signs were disposed of inappropriately. A total of 17 tritium exit signs were removed from a church located in Topeka, Kansas, six signs were reported improperly disposed of with 11 remaining in the possession of the owner and later disposed of properly. The church had contracted with EMCOR to dispose of the signs and replace them with LED exit signs. The sub contractor, Mid-West Signs, reported they unintentionally disposed of six of the signs in the trash. Before this error was realized the trash was collected and the signs were determined unrecoverable. The signs were uninstalled on November 3, 2022; however it is unclear at this time when the signs might have been placed in the trash. This is an initial report and the incident is still open pending an investigation and management review."
THIS MATERIAL EVENT CONTAINS A 'Less than Cat 3' LEVEL OF RADIOACTIVE MATERIAL
Sources that are "Less than IAEA Category 3 sources," are either sources that are very unlikely to cause permanent injury to individuals or contain a very small amount of radioactive material that would not cause any permanent injury. Some of these sources, such as moisture density gauges or thickness gauges that are Category 4, the amount of unshielded radioactive material, if not safely managed or securely protected, could possibly - although it is unlikely - temporarily injure someone who handled it or were otherwise in contact with it, or who were close to it for a period of many weeks. For additional information go to http://www-pub.iaea.org/MTCD/publications/PDF/Pub1227_web.pdf
```

**`20231011en_en56792`** (<https://www.nrc.gov/documents-reports/document-collections/events-reports-associated-with/event-notification-reports/2023/20231011en#en56792>)

```
AGREEMENT STATE REPORT - STUCK SOURCE
The following information was provided by the Maryland Department of the Environment Radiological Health Program (MDE/RHP) via email:
"On October 11, 2023 at 1558 EDT, the Maryland Department of the Environment Radiological Health Program was contacted via phone from the Radiation Safety Officer (RSO) of Testing Technologies, Inc. (TTI), and reported that a source disconnect had occurred on 10/10/2023, at about 1000 EDT while working at College Park, Maryland. TTI has an active authorization and reciprocity recognition to practice industrial radiography in Maryland with US NRC license (number 45-25007-01). TTI has a Virginia (Maryland reciprocity license number 94-031-01) and an NRC license; and they are also authorized to retrieve sources. The radiography device was QSA Global, Sentinel 880, device serial number D6011, which contains 50 Ci of Ir-192.
"The incident occurred when the TTI radiographer was taking images of a pipe in the well and while cranking back at finishing, the source became stuck at about the half-way position. The radiographer was aware that the source disconnection from the tube had happened and the source was lodged in a 14 feet deep hole. The radiographer later retrieved the source. The radiographer reported the incident to the TTI RSO.
"The RSO reported that there was no exposure to the public. A dose of 40 mrem was received by the radiographer.
"MDE/RHP will finalize a reactive investigation."
```

**`20240326en_en57052`** (<https://www.nrc.gov/documents-reports/document-collections/events-reports-associated-with/event-notification-reports/2024/20240326en#en57052>)

```
AGREEMENT STATE REPORT - DETACHED SOURCE
The following was received from the Texas Department of State Health Services (the Department) via phone and email:
"On March 26, 2024, the Department was notified by the licensee's radiation safety office (RSO) that earlier this day a radiography crew had a source disconnect while using a SPEC 150 exposure device. The device contained a 23 curie, iridium-192 source.
"The disconnect occurred on the first shot of the day. The RSO reported that the radiographers had completed set up for the first shot but had failed to properly connect the guide tube to the camera. When the radiographers cranked the source out and it hit the collimator, the guide tube popped loose from the camera. The radiographer immediately attempted to crank the source back into the camera but when the source reached the end of the guide tube the source pigtail disconnected from the drive cable.
"The radiographers set up new boundaries and contacted the RSO. An RSO from a nearby office responded to the location. The RSO was wearing a self-reading dosimeter (SRD), alarming rate meter, and TLD [thermoluminescent dosimeter] exposure badge. The RSO placed the camera on the source for shielding, attached the source back to the drive cable, and retracted the source into the camera. The responding RSO's SRD was reading off scale after retracting the source. The badge has been sent to the licensee's dosimetry processor for emergency processing.
"The licensee does not believe any individual exceeded any limit due to this event. Additional information will be provided as it is received in accordance with SA-300."
Texas Incident # 10095
```

**`20250726en_en57829`** (<https://www.nrc.gov/documents-reports/document-collections/events-reports-associated-with/event-notification-reports/2025/20250726en#en57829>)

```
UNANALYZED CONDITION
The following information was provided by the licensee via phone and email:
"The facility is in a safe and stable configuration. Additionally, the facility is not [and] has never been in a flooded state, and no accident has occurred.
"Urenco USA has stored three end-of-life uranium hexafluoride traps in the ventilated room on the first floor of the cylinder receipt and dispatch building (CRDB). These traps were previously installed in the system on the second floor of the process services corridor (PSC). While installed, these traps have been analyzed as safe for movement and interaction without any external controls.
"Flooding is not considered a credible event for the second floor of the PSC. However, these traps have been moved to the first floor of the CRDB for storage where flooding is a credible event. A first-floor condition of flooding with the traps has not been modeled in the nuclear criticality safety analysis (NCSA).
"The storage of traps in the first-floor ventilated room potentially falls outside of the normal operating conditions analyzed in NCSA and integrated safety analysis (ISA) related documentation and results in the facility being in a state that was different from analyzed in the ISA.
"Corrective actions have begun."
The following additional information was obtained from the licensee in accordance with Headquarters Operations Officers Report Guidance:
Personnel access to the area has been restricted pending completion of the evaluation.
```

**`20251102en_en58018`** (<https://www.nrc.gov/documents-reports/document-collections/events-reports-associated-with/event-notification-reports/2025/20251102en#en58018>)

```
AUTOMATIC REACTOR SCRAM
The following information was provided by the licensee via phone and email:
"At 1346 CST with Unit 1 in mode 1 at 100 percent power, the reactor automatically tripped on turbine control valve fast closure due to a generator lockout. The trip was not complex with all systems responding normally post-trip. Due to the reactor protection system actuation while critical, this event is being reported as a four-hour, non-emergency notification per 10 CFR 50.72(b)(2)(iv)(B).
"Operations responded using emergency operating procedures and stabilized the plant in mode 3. Decay heat is being removed by discharging steam to the main condenser using the turbine bypass valves. Unit 2 is not affected.
"There was no impact on the health and safety of the public or plant personnel. The NRC Resident Inspector has been notified."
```

**`20251202en_en58059`** (<https://www.nrc.gov/documents-reports/document-collections/events-reports-associated-with/event-notification-reports/2025/20251202en#en58059>)

```
AGREEMENT STATE REPORT - LEAKING SOURCE
The following information was provided by the Pennsylvania Department of Environmental Protection, Bureau of Radiation Protection (the Department), via email:
"On November 21, 2025, the licensee was performing a routine sealed source leak test and discovered that a Cs-137 vial reference standard (model RV-137-200U, S/N 1710-68-8) was leaking. The licensee used a Capintec CRC 55tW well counter to determine if the source was leaking or contaminated. The source container was wipe-tested on the inside and found to also be contaminated. The dose calibrator dipper was very slightly contaminated and also removed from service. All other equipment associated with the source was wipe tested and found to be free of contamination. The source was immediately removed from service. The sealed source was replaced in the original lead container and placed into gloves and a plastic bag along with all associated wipes and the dose calibrator dipper. The licensee will package the material and send it for disposal. The estimated activity of the source was 170 microcuries, and the leak test results were 0.0139 microcuries.
"The Department will perform a reactive inspection. More information will be provided as it is received."
Event report number: PA250016
```

**`20260519en_en58282`** (<https://www.nrc.gov/documents-reports/document-collections/events-reports-associated-with/event-notification-reports/2026/20260519en#en58282>)

```
TECHNICAL SPECIFICATION ABNORMAL OCCURRENCE
The following information was provided by the licensee via phone and email:
"On May 17, 2026, at 0457 CDT, the control room received a firemain low pressure alarm with indication reading 0 psi. The firemain provides the source of water to the emergency pool fill system as required by Technical Specification 3.9.b. At 0501 it was confirmed this was an actual firemain rupture and not just an indication. At 0502 the reactor was manually scrammed. At 0514 the ruptured firemain was discovered and isolated shortly thereafter to restore pressure. Subsequently, permission for the reactor restart was received from the facility director and the reactor was restarted at 1245.
"The 12-inch firemain was found split from fitting to fitting. The cause is still being investigated."
The following additional information was obtained from the licensee in accordance with Headquarters Operations Officers Report Guidance:
At the time of notification, the reactor was in the shutdown condition for normal planned maintenance.
```

---

## (c) Near-duplicate trigger measurement

Run against the full 33,725-document corpus above, exact-deduplicated first (per
`dedup.py`'s course-default normalization: strip + lowercase, SHA-256 identity),
then the pre-registered 5-shingle Jaccard measurement on a 2,000-document sample of
what survives:

| step | count |
| --- | --- |
| raw documents | 33,725 |
| exact duplicates removed | 5,822 |
| unique documents after exact dedup | 27,903 |
| sample size (seed `20260913`) | 2,000 |
| pairs compared | 1,999,000 |
| pairs above 0.8 Jaccard | 9 |
| **share above threshold** | **0.000005 (0.0005%)** |
| pre-registered trigger | fires above 5% (0.05) |
| **trigger fires?** | **No** |

Exact dedup alone removes 17.3% of the raw corpus — the same incident is routinely
republished verbatim across NRC's own multi-day report cycle. The near-duplicate
share on what survives is five orders of magnitude below the pre-registered 5%
trigger; per the M2 brief, **MinHash-LSH is not implemented** — exact dedup is the
whole story for this corpus.

One of the four exact-1.0-similarity pairs was inspected directly to understand why
anything survived exact dedup at all: `20041126en_en41208` and `20041124en_en41208`
are the same stolen-radiography-camera event, republished on two different report
days, byte-identical after `.split()` but differing in a single interior line break
(`"...CAMERA \nThe State..."` vs `"...CAMERA\n The State..."`) — invisible to
word-level shingling, but enough to change the SHA-256 identity `dedup.py`'s exact
match keys on. This is exactly the class of near-duplicate the measurement exists
to catch, and it is caught; there simply are not enough of them (9 pairs in
1,999,000) to justify building MinHash-LSH.

---

## (d) Total measured yield against the 30M-token floor

| | whitespace tokens |
| --- | --- |
| Event notifications | 7,944,987 |
| Information Notices | 404,615 |
| Bulletins | 273,697 |
| Generic Letters | 747,952 |
| Regulatory Issue Summaries | 91,554 |
| **Narrative corpus total** | **9,462,805** |
| Status code book (reported separately, not pooled) | 938 |
| PHMSA (not staged — see (e)) | not counted |

**The corpus measures 9,462,805 whitespace tokens, stated plainly: about 9.5M
against the 30M-token floor set in the M2 brief — roughly 31.5% of the floor, not
met.** ADR-0016 already carries the reason and the brief's own re-reading of what
that means: with only one Tier-1 source (`nrc.gov`) reachable by a permitted,
robots.txt-compliant route, "the pipeline and its reports are the gate, not the
token count" (ADR-0016, "Floor and target, re-read against the evidence"). PHMSA
landing (pending a manual download, see (e)) would add to this total but its
narrative field has not yet been profiled, so no number is added on its account
here — ADR-0016 explicitly declines to estimate PHMSA's yield before the file is
inspected.

A whitespace-token count is not a fitted-tokenizer count; it is expected to be
somewhat higher than a BPE count over the same text (each whitespace-delimited
word typically becomes close to, but not exactly, one BPE token at this vocabulary
size), so this figure is a reasonable but not exact proxy for what M2c would
measure once BPE is fit.

---

## (e) Revised ADR-0016 and the PHMSA route result

ADR-0016 (`docs/DECISIONS.md`) already carries the full revision this checkpoint
references; not reproduced here in full. Summary of its current state:

- **Restructured** into a four-column table per Tier-1 source (automated route /
  manual route / estimated narrative yield / decision), separating "this project's
  crawler cannot fetch this" from "no permitted route exists at all."
- **PHMSA**: re-tested via `data.transportation.gov` (a second, independent host
  from `phmsa.dot.gov`'s blocking Akamai front). The named dataset
  (`qdme-9bbm`, "Pipeline Incident Flagged Files") is metadata-only — an `"href"`
  pointer, not an independently hosted export — and its access point resolves back
  to `phmsa.dot.gov`, which two independent automated clients (`requests` and
  Claude's `WebFetch`) both received `403 Forbidden` from. Status changed from
  `excluded` to **`manual_pending`**: the automated route is closed, but a human
  downloading the named file in their own browser and recording its URL, date and
  hash is ordinary provenance, not a workaround. The exact file is named:
  `https://www.phmsa.dot.gov/sites/phmsa.dot.gov/files/data_statistics/pipeline/PHMSA_Pipeline_Safety_Flagged_Incidents.zip`.
  **Result as of this checkpoint: the file has not yet appeared at
  `data/raw/text/phmsa/`.** `faultline inspect phmsa` (`src/faultline/data/text/phmsa_manual.py`)
  is built, tested and waiting — it will hash the archive, record
  `retrieval_method="manual, author, browser"` in the manifest, and profile every
  tabular member read-only (rows, narrative-column detection, whitespace-token
  estimate) the moment it lands, with no pipeline run. Its numbers are not in (a)
  or (d) above for exactly that reason.
- **DOE OE-417**: exclusion reason corrected from "unreachable" (true only of the
  original publishing host, `www.oe.netl.doe.gov`, IPv6-only from this network) to
  **thin**: 341 rows, 2023-only, a 27-entry closed code book where a narrative
  field would be, 9,614 whitespace tokens total. A self-caught correction is
  recorded alongside it: the ORNL mirror query this measurement came from itself
  violated ORNL's own `robots.txt` (`Disallow: /api/`, `Allow:` carved out for
  Googlebot only) — not relied on further, and the direct cause of the pre-request
  robots.txt gate below.
- **NRC LERs**: exclusion confirmed independently (`lersearch.inl.gov/robots.txt`:
  `Disallow: /`; data.gov's catalogue entry names the search UI as its sole
  resource, no bulk export). Route forward: a written bulk-export request to NRC,
  recorded as such if it is ever made.
- **Generic-communications yield table corrected**: Information Notices 439→424,
  Generic Letters 574→563, Regulatory Issue Summaries 180→**53** — the second PDF
  path found while investigating reg-issues (`/sites/default/files/doc_library/...`,
  distinct from the ADAMS `/docs/` path, 200 OK but still a PDF) was silently
  miscounted as native HTML by the original filter. The crawl's actually-staged
  counts were correct throughout; the ADR's first-published reconnaissance number
  was not, for reg-issues specifically.
- **Pre-request robots.txt gate**: `NrcTextClient` now fetches and parses a host's
  `robots.txt` once, before its first request to that host, and refuses any
  disallowed path with a logged reason (`TestRobotsGating`,
  `tests/download/test_nrc_text.py`, 7 tests, asserts a disallowed URL is never
  passed to the transport). ADR-0016 records the two ORNL `/api/` queries as the
  reason this exists.
- **Manifest sharding**: `nrc_event_notifications`'s manifest (32,455 documents)
  outgrew the repository's 5MB large-file limit twice as the source's real size
  became known. Per the user's explicit direction, the limit was not raised;
  the manifest is now sharded per report year as compact JSONL under
  `data/cards/manifests/nrc_event_notifications/`, each shard well under 5MB
  (largest: 702KB). Dated note in `docs/ROADMAP.md`'s M0 git-hygiene line.

---

## Summary

- Corpus assembled and measured, not built past that: no BPE fit, no shards, no
  pretraining, no dataset cards.
- 33,725 documents, 9,462,805 whitespace tokens across five `nrc.gov` sources —
  about 31.5% of the 30M-token floor.
- Near-duplicate trigger measured and does **not** fire (0.0005% vs. 5%); exact
  dedup is the whole deduplication story for this corpus.
- Two real extraction bugs found and fixed during this checkpoint's preparation
  (PDF-path miscounting; midera-template regex brittleness), both with regression
  tests built from real captured pages, both already reflected in the numbers
  above (not carried forward as a known gap).
- Every event-notification document now carries its template era as measured
  ground truth, not inferred from date; the per-era breakdown in (a) is exact.
- PHMSA remains unstaged — the route is open (manual, browser, ordinary
  provenance) and the exact file is named, but the file has not yet been placed
  in `data/raw/text/phmsa/`.

**Stopping here per instruction, pending review.**

---

## Addendum, 2026-09-13: Gate-6 corrections, re-measured (a) and (d)

The user reviewed this checkpoint and accepted the extraction across all three
eras. Before the BPE fit, three corrections were required; this addendum
records them and re-measures (a) and (d) against the corrected corpus. Full
detail and the decision record are in ADR-0016 (`docs/DECISIONS.md`); this
section is the numbers.

**What changed.** Two declared rules were added to `configs/data/text_v1.yaml`
and, for the first time, the full declared pipeline (clean -> filter -> dedup
-> pii -> final) was run against the real assembled corpus --
`faultline text run --config configs/data/text_v1.yaml --stage all`, run id
`20260913-142340_all_text_2a6ec5b7`, reports at
`reports/data/20260913-142340_all_text_2a6ec5b7/`. Everything in this addendum
is read from that run's generated reports and from the corrected final corpus
on disk, not re-derived by hand.

1. **Source-aware (keyed) dedup, `dedup.keyed`** (`src/faultline/data/text/keyed_dedup.py`):
   for `nrc_event_notifications`, keep one document per event number -- the
   latest report day. The M2b pre-registered near-duplicate trigger was a
   random-pair sample; with 21,882 distinct event numbers in the corpus, a
   random pair landing on two revisions of the same event is a near-impossible
   draw, so the trigger could not see this pattern -- the wrong instrument for
   this corpus, the author's own correction to the M2b brief, not an error in
   how the trigger was run. Measured (in real pipeline order: post-clean,
   post-filter, post-exact-dedup, 27,662 `nrc_event_notifications` documents
   reaching this rule): 21,882 distinct event numbers, 3,901 with more than one
   surviving revision. Confirmation that "keep the latest" is correct, not
   merely plausible: 40 sampled multi-revision groups, latest never shorter
   than earliest (40/40); normalized, the earlier document's post-title body
   is a substring of the later one in 30/40 (the rest differ only in a
   reworded opening line, not a rewrite). **4,521 documents removed,
   1,214,427 whitespace tokens** (7,602,753 before this rule -> 6,388,326
   after, at the point in the pipeline it runs).

2. **Two declared fixed-boilerplate rules, `clean.boilerplate`**
   (`src/faultline/data/text/boilerplate.py`): the extractor's own
   `EN Revision Imported Date: .../EN Revision Text:` metadata lines (1,316
   documents), and the fixed IAEA "Less than Cat 3" source-category
   explanation, from "THIS MATERIAL EVENT CONTAINS" through the
   `Pub1227_web.pdf` URL where present (2,616 occurrences) or through the
   sentence before it where the URL is absent -- the same fixed paragraph,
   used since at least 2005, found while building this rule and not in the
   original brief (866 occurrences). **1,316 + 3,482 = 4,798 matches removed,
   419,746 whitespace tokens** (isolated on the raw corpus, before any other
   cleaning step: 9,462,805 -> 9,043,059). Three further occurrences carry a
   source-side URL typo and are not matched (documented, not chased).

   The general check the brief also asked for: every document split into
   blank-line-delimited paragraphs, normalized, hashed, counting how many
   *documents* each distinct paragraph appears in (not raw occurrences). Run
   against the raw corpus, exactly 7 paragraphs recur in more than 100
   documents:

   | paragraph (first 120 chars) | documents |
   | --- | --- |
   | The licensee notified the NRC Resident Inspector. | 442 |
   | The following text is a portion of a facsimile received from the licensee: | 377 |
   | The licensee notified the NRC resident inspector. | 360 |
   | The NRC Resident Inspector was notified. | 257 |
   | The NRC Resident Inspector was notified of this event by the licensee. | 253 |
   | The NRC resident inspector has been informed of this event by the licensee. | 108 |
   | THE LICENSEE INFORMED THE NRC RESIDENT INSPECTOR. | 104 |

   Every one is a short, genuine, formulaic narrative sentence that recurs
   because many independent incident reports end the same way -- not page
   furniture. **None are stripped.** Neither declared boilerplate rule above
   shows up in this list: both are joined to document-specific text by a
   single newline rather than a blank line, so neither is ever its own
   paragraph -- a stated limitation of paragraph-level hashing as a
   *discovery* method; it did not need to find them, since they were already
   found and matched by direct pattern first.

### (a) re-measured: event notifications by template era

Now measured on the corrected, fully-pipelined final corpus (cleaned,
filtered, deduped -- exact and keyed --, PII-scrubbed):

| era | documents (was) | documents (now) | whitespace tokens (was) | whitespace tokens (now) |
| --- | --- | --- | --- | --- |
| legacy | 6,263 | 4,614 | 1,359,413 | 971,216 |
| midera | 22,523 | 13,995 | 5,724,541 | 3,286,311 |
| modern | 3,669 | 3,273 | 861,033 | 681,624 |
| **total** | **32,455** | **21,882** | **7,944,987** | **4,939,151** |

The drop is almost entirely keyed dedup (revisions collapsed to their latest)
concentrated in `midera`, which is also the era the original checkpoint
identified as most affected by the fixed-regex undercount and, separately,
where most multi-revision event chains live -- consistent, not a new anomaly.
A small further share in every era is the filter stage running for the first
time (see below) and boilerplate stripping occasionally shrinking a document
that was mostly IAEA/header boilerplate.

### (a) re-measured: the four generic-communications sources

| source | documents (was) | documents (now) | whitespace tokens (was) | whitespace tokens (now) |
| --- | --- | --- | --- | --- |
| Information Notices | 424 | 422 | 404,615 | 399,881 |
| Bulletins | 230 | 228 | 273,697 | 270,290 |
| Generic Letters | 563 | 556 | 747,952 | 686,503 |
| Regulatory Issue Summaries | 53 | 53 | 91,554 | 91,537 |

These four sources have no event-number revision structure (`dedup.keyed`
never touches them) and essentially no IAEA/EN-revision boilerplate; their
small movement is exact dedup and the filter/PII stages running for the first
time, not the two Gate-6 corrections.

**New this run, for completeness (neither existed as a measurement in the
original checkpoint, which never ran the pipeline past raw assembly):** the
filter stage, run for the first time, dropped 253 of 33,725 cleaned documents
(171 `repeated_lines`, 79 `min_chars`, 3 `max_chars`) -- expected to include a
handful of documents whose entire content was boilerplate now stripped down
to nothing, though this was not run before to compare against. The PII stage
masked 332 emails and 1,490 phone numbers, changing the corpus's whitespace
token count by a further -964 tokens (placeholders are shorter than what they
replace).

### (d) re-measured: total yield against the 30M-token floor

| | whitespace tokens (was) | whitespace tokens (now) |
| --- | --- | --- |
| Event notifications | 7,944,987 | 4,939,151 |
| Information Notices | 404,615 | 399,881 |
| Bulletins | 273,697 | 270,290 |
| Generic Letters | 747,952 | 686,503 |
| Regulatory Issue Summaries | 91,554 | 91,537 |
| **Narrative corpus total** | **9,462,805** | **6,387,362** |

**The corrected corpus measures 6,387,362 whitespace tokens -- about 21.3% of
the 30M-token floor, down from the original checkpoint's 31.5%.** This is a
real drop, not a regression to explain away: the original figure counted
33,725 raw, un-deduplicated-by-revision, boilerplate-laden documents; this one
counts 23,141 documents that are each a genuine, once-represented incident
narrative, cleaned of extractor metadata and fixed IAEA text, after the actual
declared pipeline ran end to end for the first time. ADR-0016's own position
holds unchanged: with one reachable Tier-1 source, "the pipeline and its
reports are the gate, not the token count" -- and this number is now the
pipeline's real output, not raw assembly's.

### PHMSA gate

**`data/raw/text/phmsa/` is still empty as of this addendum (checked
2026-09-13, after 1-3 above were completed).** `faultline inspect phmsa` is
built, tested and waiting; it has not run because the file has not appeared.
Per the standing instruction: the BPE fit does not start until this file is
staged and folded in, or the author explicitly says to proceed without it.

**Stopping here: corrections 1-3 are complete, and PHMSA has not appeared.
M2c (BPE fit) onward is not started, pending the author's PHMSA decision.**
