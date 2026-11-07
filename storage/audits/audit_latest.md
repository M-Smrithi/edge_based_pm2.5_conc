# Data audit

Generated 2026-10-23T10:55:49+00:00 from `/home/claude/new_dataset_incoming`.

## Summary

| Item | Count |
|---|---|
| Files audited | 223 |
| Verdict `accepted` | 17 |
| Verdict `accepted_recovered` | 124 |
| Verdict `pending_review` | 79 |
| Verdict `rejected` | 3 |
| Usable files (accepted + recovered) | 141 |
| Usable valid rows (PM2.5 present, ≥1 sensor) | 3,310,820 |
| …of which complete-case (all 12 sensors) | 1,598,179 |
| Files lacking a PM2.5 target | 3 |
| Pending review (sensor unavailable / unit unverified) | 79 |
| Byte-identical duplicate groups | 0 |

## stations_info.csv

Found: **True** (/home/claude/aiot-platform/storage/metadata/stations_info.csv); rows: 453; station codes verified against it: 223/223. Metadata is optional: without it stations are still processed, only state/city labels are unavailable.

## Usable as-is (17)

| File | Rows | Valid rows | Period | Notes |
|---|---|---|---|---|
| AP001.csv | 59150 | 54322 | 2016-07-01 → 2023-03-31 |  |
| AP002.csv | 51864 | 14192 | 2017-05-01 → 2023-03-31 |  |
| DL002.csv | 116112 | 64077 | 2010-01-01 → 2023-03-31 |  |
| DL013.csv | 104441 | 72576 | 2011-05-02 → 2023-03-31 |  |
| DL014.csv | 103728 | 71167 | 2011-06-01 → 2023-03-31 |  |
| DL015.csv | 93480 | 63851 | 2012-08-01 → 2023-03-31 |  |
| GJ001.csv | 108559 | 57324 | 2010-11-11 → 2023-03-31 |  |
| HR003.csv | 64272 | 53532 | 2015-12-01 → 2023-03-31 |  |
| KA002.csv | 116112 | 52723 | 2010-01-01 → 2023-03-31 |  |
| KL001.csv | 50747 | 42881 | 2017-06-16 → 2023-03-31 |  |
| MH002.csv | 116112 | 26108 | 2010-01-01 → 2023-03-31 |  |
| MH004.csv | 67944 | 57225 | 2015-07-01 → 2023-03-31 |  |
| UP002.csv | 116112 | 62307 | 2010-01-01 → 2023-03-31 |  |
| UP003.csv | 109560 | 69893 | 2010-10-01 → 2023-03-31 |  |
| UP004.csv | 109560 | 64720 | 2010-10-01 → 2023-03-31 |  |
| UP005.csv | 109489 | 65213 | 2010-10-03 → 2023-03-31 |  |
| WB002.csv | 63229 | 40598 | 2016-01-13 → 2023-03-31 |  |

## Usable after verified header recovery (alias / SI unit conversion) (124)

| File | Rows | Valid rows | Period | Notes |
|---|---|---|---|---|
| AP003.csv | 50400 | 44691 | 2017-07-01 → 2023-03-31 | WD←WD (degree) |
| AP004.csv | 48802 | 46344 | 2017-09-05 → 2023-03-31 | WD←WD (degree) |
| AP005.csv | 46880 | 42362 | 2017-11-24 → 2023-03-31 | WD←WD (degree) |
| AP006.csv | 5432 | 5179 | 2022-08-17 → 2023-03-31 | WD←WD (degree) |
| AP007.csv | 3127 | 2717 | 2022-11-21 → 2023-03-31 | WD←WD (degree) |
| AP008.csv | 3280 | 2979 | 2022-11-15 → 2023-03-31 | WD←WD (degree) |
| AP009.csv | 1689 | 1244 | 2023-01-20 → 2023-03-31 | WD←WD (degree) |
| AP010.csv | 1593 | 1348 | 2023-01-24 → 2023-03-31 | WD←WD (degree) |
| AR001.csv | 17655 | 7581 | 2021-03-26 → 2023-03-31 | WD←WD (degree) |
| AS001.csv | 35808 | 33733 | 2019-03-01 → 2023-03-31 | WD←WD (degree) |
| AS002.csv | 19764 | 17837 | 2020-12-28 → 2023-03-31 | WD←WD (degree) |
| AS003.csv | 4641 | 3724 | 2022-09-19 → 2023-03-31 | WD←WD (degree) |
| AS004.csv | 4400 | 3901 | 2022-09-29 → 2023-03-31 | WD←WD (degree) |
| AS005.csv | 3081 | 2883 | 2022-11-23 → 2023-03-31 | WD←WD (degree) |
| AS006.csv | 2462 | 2420 | 2022-12-19 → 2023-03-31 | WD←WD (degree) |
| AS007.csv | 2390 | 2139 | 2022-12-22 → 2023-03-31 | WD←WD (degree) |
| AS008.csv | 1881 | 1747 | 2023-01-12 → 2023-03-31 | WD←WD (degree) |
| AS009.csv | 744 | 728 | 2023-03-01 → 2023-03-31 | WD←WD (degree) |
| BR021.csv | 11864 | 10694 | 2021-11-22 → 2023-03-31 | WD←WD (degree) |
| BR022.csv | 12079 | 7790 | 2021-11-13 → 2023-03-31 | WD←WD (degree) |
| BR023.csv | 11864 | 11056 | 2021-11-22 → 2023-03-31 | WD←WD (degree) |
| BR025.csv | 12079 | 10081 | 2021-11-13 → 2023-03-31 | WD←WD (degree) |
| BR026.csv | 11864 | 11010 | 2021-11-22 → 2023-03-31 | WD←WD (degree) |
| BR027.csv | 11864 | 6952 | 2021-11-22 → 2023-03-31 | WD←WD (degree) |
| BR028.csv | 11863 | 8946 | 2021-11-22 → 2023-03-31 | WD←WD (degree) |
| BR029.csv | 11863 | 10458 | 2021-11-22 → 2023-03-31 | WD←WD (degree) |
| BR031.csv | 12079 | 9377 | 2021-11-13 → 2023-03-31 | WD←WD (degree) |
| BR032.csv | 11863 | 10158 | 2021-11-22 → 2023-03-31 | WD←WD (degree) |
| BR033.csv | 11289 | 10164 | 2021-12-16 → 2023-03-31 | WD←WD (degree) |
| BR034.csv | 8960 | 7063 | 2022-03-23 → 2023-03-31 | WD←WD (degree) |
| BR035.csv | 8672 | 5652 | 2022-04-04 → 2023-03-31 | WD←WD (degree) |
| CG004.csv | 3728 | 1991 | 2022-10-27 → 2023-03-31 | WD←WD (degree) |
| CG005.csv | 3873 | 2191 | 2022-10-21 → 2023-03-31 | WD←WD (degree) |
| CG006.csv | 3873 | 2217 | 2022-10-21 → 2023-03-31 | WD←WD (degree) |
| CG007.csv | 3873 | 2179 | 2022-10-21 → 2023-03-31 | WD←WD (degree) |
| CG008.csv | 3873 | 1713 | 2022-10-21 → 2023-03-31 | WD←WD (degree) |
| CG009.csv | 3872 | 1888 | 2022-10-21 → 2023-03-31 | WD←WD (degree) |
| CG010.csv | 3872 | 2119 | 2022-10-21 → 2023-03-31 | WD←WD (degree) |
| CG011.csv | 1689 | 1388 | 2023-01-20 → 2023-03-31 | WD←WD (degree) |
| CG012.csv | 1760 | 1661 | 2023-01-17 → 2023-03-31 | WD←WD (degree) |
| CG013.csv | 1593 | 1391 | 2023-01-24 → 2023-03-31 | WD←WD (degree) |
| CH001.csv | 32003 | 30101 | 2019-08-06 → 2023-03-31 | WD←WD (degree) |
| CH002.csv | 14455 | 13167 | 2021-08-06 → 2023-03-31 | WD←WD (degree) |
| CH003.csv | 10189 | 9907 | 2022-01-31 → 2023-03-31 | WD←WD (degree) |
| DL005.csv | 116112 | 81036 | 2010-01-01 → 2023-03-31 | WD←WD (degree) |
| DL019.csv | 45230 | 44368 | 2018-02-01 → 2023-03-31 | WD←WD (degree) |
| DL020.csv | 45230 | 43446 | 2018-02-01 → 2023-03-31 | CO←CO (ug/m3); WD←WD (degree) |
| DL021.csv | 45230 | 42518 | 2018-02-01 → 2023-03-31 | WD←WD (degree) |
| DL022.csv | 45230 | 43719 | 2018-02-01 → 2023-03-31 | WD←WD (degree) |
| DL023.csv | 45230 | 43664 | 2018-02-01 → 2023-03-31 | CO←CO (ug/m3); WD←WD (degree) |
| DL024.csv | 45230 | 44104 | 2018-02-01 → 2023-03-31 | WD←WD (degree) |
| DL025.csv | 45230 | 44456 | 2018-02-01 → 2023-03-31 | WD←WD (degree) |
| DL026.csv | 45230 | 43183 | 2018-02-01 → 2023-03-31 | WD←WD (degree) |
| DL027.csv | 45230 | 44070 | 2018-02-01 → 2023-03-31 | CO←CO (ng/m3); WD←WD (degree) |
| DL029.csv | 44568 | 43892 | 2018-03-01 → 2023-03-31 | WD←WD (degree) |
| DL031.csv | 44568 | 42633 | 2018-03-01 → 2023-03-31 | WD←WD (degree) |
| DL033.csv | 44568 | 43131 | 2018-03-01 → 2023-03-31 | WD←WD (degree) |
| DL039.csv | 20842 | 12684 | 2020-11-13 → 2023-03-31 | WD←WD (degree) |
| GJ002.csv | 36463 | 30477 | 2019-02-01 → 2023-03-31 | WD←WD (degree) |
| GJ003.csv | 36203 | 27122 | 2019-02-12 → 2023-03-31 | WD←WD (degree) |
| GJ004.csv | 36391 | 34794 | 2019-02-04 → 2023-03-31 | WD←WD (degree) |
| GJ007.csv | 15681 | 10522 | 2021-06-16 → 2023-03-31 | WD←WD (degree) |
| GJ008.csv | 15657 | 14861 | 2021-06-17 → 2023-03-31 | WD←WD (degree) |
| GJ010.csv | 15963 | 9985 | 2021-06-04 → 2023-03-31 | WD←WD (degree) |
| GJ012.csv | 15681 | 14818 | 2021-06-16 → 2023-03-31 | WD←WD (degree) |
| GJ013.csv | 15963 | 9325 | 2021-06-04 → 2023-03-31 | WD←WD (degree) |
| GJ014.csv | 15346 | 8509 | 2021-06-30 → 2023-03-31 | WD←WD (degree) |
| HP001.csv | 9247 | 8742 | 2022-03-11 → 2023-03-31 | WD←WD (degree) |
| HR009.csv | 36999 | 34736 | 2019-01-10 → 2023-03-31 | WD←WD (degree) |
| HR011.csv | 37140 | 33858 | 2019-01-04 → 2023-03-31 | WD←WD (degree) |
| HR013.csv | 36806 | 34178 | 2019-01-18 → 2023-03-31 | WD←WD (degree) |
| HR014.csv | 37044 | 35081 | 2019-01-08 → 2023-03-31 | WD←WD (degree) |
| HR016.csv | 37075 | 31951 | 2019-01-07 → 2023-03-31 | WD←WD (degree) |
| HR017.csv | 37022 | 30992 | 2019-01-09 → 2023-03-31 | WD←WD (degree) |
| HR018.csv | 37017 | 31405 | 2019-01-09 → 2023-03-31 | WD←WD (degree) |
| HR019.csv | 37062 | 34649 | 2019-01-07 → 2023-03-31 | WD←WD (degree) |
| HR021.csv | 36998 | 33904 | 2019-01-10 → 2023-03-31 | WD←WD (degree) |
| HR022.csv | 37042 | 32594 | 2019-01-08 → 2023-03-31 | CO←CO (ug/m3); WD←WD (degree) |
| HR023.csv | 36200 | 33796 | 2019-02-12 → 2023-03-31 | WD←WD (degree) |
| HR024.csv | 36480 | 33374 | 2019-02-01 → 2023-03-31 | WD←WD (degree) |
| HR025.csv | 26959 | 18969 | 2020-03-03 → 2023-03-31 | WD←WD (degree) |
| HR026.csv | 26937 | 21296 | 2020-03-04 → 2023-03-31 | WD←WD (degree) |
| HR027.csv | 26913 | 25249 | 2020-03-05 → 2023-03-31 | WD←WD (degree) |
| HR028.csv | 26913 | 25731 | 2020-03-05 → 2023-03-31 | WD←WD (degree) |
| HR029.csv | 26962 | 22616 | 2020-03-03 → 2023-03-31 | WD←WD (degree) |
| HR030.csv | 26936 | 21988 | 2020-03-04 → 2023-03-31 | WD←WD (degree) |
| KA015.csv | 32438 | 28055 | 2019-07-19 → 2023-03-31 | WD←WD (degree) |
| KA016.csv | 32439 | 19229 | 2019-07-19 → 2023-03-31 | WD←WD (degree) |
| KA038.csv | 2625 | 2062 | 2022-12-12 → 2023-03-31 | WD←WD (degree) |
| KA039.csv | 1401 | 1173 | 2023-02-01 → 2023-03-31 | WD←WD (degree) |
| KL003.csv | 27950 | 22616 | 2020-01-22 → 2023-03-31 | WD←WD (degree) |
| KL006.csv | 27416 | 23287 | 2020-02-13 → 2023-03-31 | WD←WD (degree) |
| KL007.csv | 27326 | 22755 | 2020-02-17 → 2023-03-31 | WD←WD (degree) |
| KL008.csv | 27659 | 25080 | 2020-02-03 → 2023-03-31 | WD←WD (degree) |
| KL009.csv | 21605 | 17273 | 2020-10-12 → 2023-03-31 | WD←WD (degree) |
| UP037.csv | 14942 | 13291 | 2021-07-17 → 2023-03-31 | WD←WD (degree) |
| UP038.csv | 14720 | 13456 | 2021-07-26 → 2023-03-31 | WD←WD (degree) |
| UP039.csv | 15061 | 14279 | 2021-07-12 → 2023-03-31 | WD←WD (degree) |
| UP040.csv | 15124 | 14655 | 2021-07-09 → 2023-03-31 | WD←WD (degree) |
| UP041.csv | 15175 | 14072 | 2021-07-07 → 2023-03-31 | WD←WD (degree) |
| UP042.csv | 14720 | 8143 | 2021-07-26 → 2023-03-31 | WD←WD (degree) |
| UP043.csv | 14553 | 13298 | 2021-08-02 → 2023-03-31 | WD←WD (degree) |
| UP044.csv | 13785 | 13217 | 2021-09-03 → 2023-03-31 | WD←WD (degree) |
| UP045.csv | 13693 | 12515 | 2021-09-07 → 2023-03-31 | WD←WD (degree) |
| UP046.csv | 12153 | 11181 | 2021-11-10 → 2023-03-31 | WD←WD (degree) |
| UP048.csv | 11264 | 10285 | 2021-12-17 → 2023-03-31 | WD←WD (degree) |
| UP049.csv | 10502 | 9856 | 2022-01-18 → 2023-03-31 | WD←WD (degree) |
| UP050.csv | 10615 | 7292 | 2022-01-13 → 2023-03-31 | WD←WD (degree) |
| UP051.csv | 9824 | 6741 | 2022-02-15 → 2023-03-31 | WD←WD (degree) |
| UP052.csv | 10088 | 8579 | 2022-02-04 → 2023-03-31 | WD←WD (degree) |
| UP053.csv | 7455 | 6539 | 2022-05-25 → 2023-03-31 | WD←WD (degree) |
| UP054.csv | 7257 | 6444 | 2022-06-02 → 2023-03-31 | WD←WD (degree) |
| UP055.csv | 6775 | 6280 | 2022-06-22 → 2023-03-31 | WD←WD (degree) |
| UP056.csv | 6827 | 6374 | 2022-06-20 → 2023-03-31 | WD←WD (degree) |
| UP057.csv | 5605 | 4953 | 2022-08-10 → 2023-03-31 | WD←WD (degree) |
| WB003.csv | 59255 | 40686 | 2016-06-27 → 2023-03-31 | WD←WD (degree) |
| WB004.csv | 58640 | 19137 | 2016-07-22 → 2023-03-31 | WD←WD (degree) |
| WB005.csv | 57672 | 34383 | 2016-09-01 → 2023-03-31 | WD←WD (degree) |
| WB009.csv | 33612 | 29437 | 2019-05-31 → 2023-03-31 | WD←WD (degree) |
| WB010.csv | 34188 | 32591 | 2019-05-07 → 2023-03-31 | WD←WD (degree) |
| WB011.csv | 33542 | 32535 | 2019-06-03 → 2023-03-31 | WD←WD (degree) |
| WB012.csv | 32006 | 29727 | 2019-08-06 → 2023-03-31 | WD←WD (degree) |
| WB013.csv | 31641 | 29900 | 2019-08-21 → 2023-03-31 | WD←WD (degree) |
| WB014.csv | 31430 | 29438 | 2019-08-30 → 2023-03-31 | WD←WD (degree) |

## Potentially recoverable — needs administrator decision (79)

| File | Rows | Valid rows | Period | Notes |
|---|---|---|---|---|
| BR024.csv | 12079 | 7684 | 2021-11-13 → 2023-03-31 | NO: conversion from 'NO (mg/m3)' not supported by the data (median 570 outside range).; Sensor(s) unavailable: AT: blank unit in header |
| BR030.csv | 12079 | 9425 | 2021-11-13 → 2023-03-31 | Sensor(s) unavailable: AT: blank unit in header |
| CG001.csv | 13329 | 12694 | 2021-09-22 → 2023-03-31 | Sensor(s) unavailable: O3: no column |
| CG002.csv | 12009 | 5204 | 2021-11-16 → 2023-03-31 | Sensor(s) unavailable: RH: no column; WS: no column; WD: no column; SR: no column; AT: no column |
| CG003.csv | 3753 | 1734 | 2022-10-26 → 2023-03-31 | Sensor(s) unavailable: CO: unit 'mg/Nm3' is not verifiably convertible to mg/m3 |
| CG014.csv | 1855 | 1796 | 2023-01-13 → 2023-03-31 | Sensor(s) unavailable: SR: unit 'ug/m3' is not verifiably convertible to W/m2 |
| DL001.csv | 116112 | 76655 | 2010-01-01 → 2023-03-31 | Sensor(s) unavailable: RH: no column; WS: no column; WD: no column; SR: no column; AT: no column |
| DL003.csv | 116112 | 50828 | 2010-01-01 → 2023-03-31 | Sensor(s) unavailable: AT: blank unit in header |
| DL004.csv | 116027 | 63192 | 2010-01-04 → 2023-03-31 | Sensor(s) unavailable: AT: blank unit in header |
| DL006.csv | 116112 | 48509 | 2010-01-01 → 2023-03-31 | Sensor(s) unavailable: AT: no column |
| DL007.csv | 113962 | 24395 | 2010-03-31 → 2023-03-31 | Sensor(s) unavailable: SO2: no column |
| DL008.csv | 114635 | 46610 | 2010-03-03 → 2023-03-31 | Sensor(s) unavailable: SO2: no column; O3: unit 'ppb' is not verifiably convertible to ug/m3 |
| DL009.csv | 113168 | 48910 | 2010-05-03 → 2023-03-31 | Sensor(s) unavailable: SO2: no column |
| DL010.csv | 110648 | 51901 | 2010-08-16 → 2023-03-31 | Sensor(s) unavailable: SO2: no column |
| DL011.csv | 109905 | 44108 | 2010-09-16 → 2023-03-31 | Sensor(s) unavailable: SO2: no column |
| DL012.csv | 104472 | 73455 | 2011-05-01 → 2023-03-31 | Sensor(s) unavailable: WS: blank unit in header |
| DL016.csv | 81792 | 46187 | 2013-12-01 → 2023-03-31 | Sensor(s) unavailable: SO2: no column |
| DL017.csv | 81039 | 52229 | 2014-01-01 → 2023-03-31 | Sensor(s) unavailable: SO2: no column |
| DL028.csv | 44568 | 41209 | 2018-03-01 → 2023-03-31 | Sensor(s) unavailable: NOx: unit 'ug/m3' is not verifiably convertible to ppb; WD: unit 'degree C' is not verifiably convertible to degrees |
| DL030.csv | 44568 | 43786 | 2018-03-01 → 2023-03-31 | Sensor(s) unavailable: NOx: unit 'ug/m3' is not verifiably convertible to ppb |
| DL032.csv | 44568 | 42927 | 2018-03-01 → 2023-03-31 | Sensor(s) unavailable: WS: blank unit in header; SR: blank unit in header |
| DL034.csv | 41574 | 40783 | 2018-07-03 → 2023-03-31 | Sensor(s) unavailable: WD: blank unit in header |
| DL035.csv | 41550 | 40489 | 2018-07-04 → 2023-03-31 | Sensor(s) unavailable: SO2: blank unit in header; WD: blank unit in header |
| DL036.csv | 41574 | 40177 | 2018-07-03 → 2023-03-31 | Sensor(s) unavailable: WD: blank unit in header |
| DL037.csv | 41574 | 39546 | 2018-07-03 → 2023-03-31 | Sensor(s) unavailable: RH: blank unit in header; AT: blank unit in header |
| DL038.csv | 38434 | 36605 | 2018-11-11 → 2023-03-31 | Sensor(s) unavailable: WS: no column; AT: blank unit in header |
| DL040.csv | 20842 | 14694 | 2020-11-13 → 2023-03-31 | Sensor(s) unavailable: SR: no column |
| GJ005.csv | 36463 | 33958 | 2019-02-01 → 2023-03-31 | Sensor(s) unavailable: RH: blank unit in header |
| GJ006.csv | 27945 | 18558 | 2020-01-22 → 2023-03-31 | Sensor(s) unavailable: O3: no column; RH: no column; WS: no column; WD: no column; SR: no column; AT: no column |
| GJ009.csv | 15681 | 9080 | 2021-06-16 → 2023-03-31 | Sensor(s) unavailable: AT: unit 'degree' is not verifiably convertible to deg C |
| GJ011.csv | 15963 | 8602 | 2021-06-04 → 2023-03-31 | Sensor(s) unavailable: SR: no column |
| GJ015.csv | 15681 | 10841 | 2021-06-16 → 2023-03-31 | Sensor(s) unavailable: AT: unit 'degree' is not verifiably convertible to deg C |
| GJ016.csv | 15681 | 14523 | 2021-06-16 → 2023-03-31 | Sensor(s) unavailable: SR: no column |
| GJ017.csv | 3559 | 3168 | 2022-11-03 → 2023-03-31 | Sensor(s) unavailable: O3: no column |
| HR001.csv | 109992 | 59245 | 2010-09-13 → 2023-03-31 | Sensor(s) unavailable: PM10: no column |
| HR002.csv | 64096 | 50589 | 2015-12-01 → 2023-03-31 | Sensor(s) unavailable: PM10: no column |
| HR004.csv | 63519 | 49890 | 2016-01-01 → 2023-03-31 | Sensor(s) unavailable: AT: no column |
| HR005.csv | 56382 | 37915 | 2016-10-24 → 2023-03-31 | Sensor(s) unavailable: NO: blank unit in header; SO2: no column; O3: blank unit in header; RH: no column; WS: no column; WD: no column; SR: no column; AT: no co |
| HR006.csv | 42994 | 34451 | 2018-05-05 → 2023-03-31 | Sensor(s) unavailable: RH: no column; WS: no column; WD: no column; SR: no column; AT: no column |
| HR007.csv | 37309 | 31482 | 2018-12-28 → 2023-03-31 | Sensor(s) unavailable: RH: no column; WS: no column; WD: no column; SR: no column; AT: no column |
| HR008.csv | 37069 | 32873 | 2019-01-07 → 2023-03-31 | Sensor(s) unavailable: SR: no column |
| HR010.csv | 37210 | 32353 | 2019-01-01 → 2023-03-31 | Sensor(s) unavailable: WS: unit 'ug/m3' is not verifiably convertible to m/s; SR: unit 'ug/m3' is not verifiably convertible to W/m2 |
| HR012.csv | 37162 | 33698 | 2019-01-03 → 2023-03-31 | Sensor(s) unavailable: WD: unit 'degree C' is not verifiably convertible to degrees |
| HR015.csv | 37062 | 35452 | 2019-01-07 → 2023-03-31 | Sensor(s) unavailable: AT: unit 'ug/m3' is not verifiably convertible to deg C |
| HR020.csv | 37059 | 35051 | 2019-01-07 → 2023-03-31 | Sensor(s) unavailable: RH: no column |
| JH001.csv | 51864 | 8074 | 2017-05-01 → 2023-03-31 | Sensor(s) unavailable: NOx: no column; AT: blank unit in header |
| JH002.csv | 774 | 691 | 2023-02-27 → 2023-03-31 | Sensor(s) unavailable: RH: no column; WS: no column; WD: no column; SR: no column; AT: no column |
| JK001.csv | 18733 | 16052 | 2021-02-09 → 2023-03-31 | Sensor(s) unavailable: AT: no column |
| KA001.csv | 116050 | 54114 | 2010-01-03 → 2023-03-31 | Sensor(s) unavailable: AT: no column |
| KA003.csv | 116112 | 56134 | 2010-01-01 → 2023-03-31 | Sensor(s) unavailable: WS: no column; WD: no column; AT: no column |
| KA004.csv | 72273 | 33600 | 2015-01-01 → 2023-03-31 | Sensor(s) unavailable: NOx: unit 'ug/m3' is not verifiably convertible to ppb; SR: no column; AT: no column |
| KA007.csv | 41771 | 36495 | 2018-06-25 → 2023-03-31 | Sensor(s) unavailable: NOx: unit 'ug/m3' is not verifiably convertible to ppb |
| KA008.csv | 41773 | 36907 | 2018-06-25 → 2023-03-31 | Sensor(s) unavailable: NO: no column; NOx: no column; SR: no column |
| KA009.csv | 41912 | 8225 | 2018-06-19 → 2023-03-31 | Sensor(s) unavailable: NOx: unit 'ug/m3' is not verifiably convertible to ppb; SR: no column; AT: blank unit in header |
| KA010.csv | 41770 | 37049 | 2018-06-25 → 2023-03-31 | Sensor(s) unavailable: RH: unit 'W/mt2' is not verifiably convertible to %; SR: no column |
| KA011.csv | 41842 | 37712 | 2018-06-22 → 2023-03-31 | Sensor(s) unavailable: RH: unit 'W/mt2' is not verifiably convertible to %; SR: no column |
| KA012.csv | 41768 | 35812 | 2018-06-25 → 2023-03-31 | Sensor(s) unavailable: RH: unit 'W/mt2' is not verifiably convertible to %; SR: no column |
| KA013.csv | 41500 | 25169 | 2018-07-06 → 2023-03-31 | Sensor(s) unavailable: NOx: unit 'ug/m3' is not verifiably convertible to ppb; SR: no column; AT: no column |
| KA014.csv | 41575 | 38610 | 2018-07-03 → 2023-03-31 | Sensor(s) unavailable: RH: unit 'W/mt2' is not verifiably convertible to %; SR: no column |
| KA017.csv | 31017 | 28037 | 2019-09-16 → 2023-03-31 | Sensor(s) unavailable: SR: no column |
| KL002.csv | 33804 | 29086 | 2019-05-23 → 2023-03-31 | Sensor(s) unavailable: SR: no column |
| KL004.csv | 27949 | 24526 | 2020-01-22 → 2023-03-31 | Sensor(s) unavailable: SR: no column |
| KL005.csv | 27948 | 20568 | 2020-01-22 → 2023-03-31 | Sensor(s) unavailable: O3: no column; RH: no column; WS: no column; WD: no column; SR: no column; AT: no column |
| MH001.csv | 116089 | 49817 | 2010-01-01 → 2023-03-31 | Sensor(s) unavailable: AT: no column |
| MH003.csv | 116112 | 22919 | 2010-01-01 → 2023-03-31 | Sensor(s) unavailable: AT: no column |
| MH005.csv | 64272 | 52057 | 2015-12-01 → 2023-03-31 | Sensor(s) unavailable: AT: no column |
| MH006.csv | 61339 | 53217 | 2016-04-01 → 2023-03-31 | Sensor(s) unavailable: AT: no column |
| MH007.csv | 57881 | 45678 | 2016-08-23 → 2023-03-31 | Sensor(s) unavailable: AT: no column |
| MH008.csv | 57672 | 48123 | 2016-09-01 → 2023-03-31 | Sensor(s) unavailable: RH: no column; AT: no column |
| TN001.csv | 116112 | 60808 | 2010-01-01 → 2023-03-31 | Sensor(s) unavailable: AT: no column |
| TN002.csv | 116112 | 64239 | 2010-01-01 → 2023-03-31 | Sensor(s) unavailable: AT: no column |
| TN003.csv | 116112 | 63632 | 2010-01-01 → 2023-03-31 | Sensor(s) unavailable: AT: no column |
| UP001.csv | 116112 | 57063 | 2010-01-01 → 2023-03-31 | Sensor(s) unavailable: AT: no column |
| UP006.csv | 108816 | 62285 | 2010-11-01 → 2023-03-31 | Sensor(s) unavailable: AT: no column |
| UP047.csv | 11433 | 10690 | 2021-12-10 → 2023-03-31 | Sensor(s) unavailable: AT: unit 'degree' is not verifiably convertible to deg C |
| WB001.csv | 64272 | 17437 | 2015-12-01 → 2023-03-31 | Sensor(s) unavailable: RH: no column |
| WB006.csv | 45538 | 43545 | 2018-01-19 → 2023-03-31 | Sensor(s) unavailable: NOx: unit 'ug/m3' is not verifiably convertible to ppb; AT: no column |
| WB007.csv | 45230 | 40927 | 2018-02-01 → 2023-03-31 | Sensor(s) unavailable: RH: blank unit in header |
| WB008.csv | 45240 | 42822 | 2018-02-01 → 2023-03-31 | Sensor(s) unavailable: SO2: blank unit in header; SR: blank unit in header; AT: no column |

## Unusable for supervised training (3)

| File | Rows | Valid rows | Period | Notes |
|---|---|---|---|---|
| DL018.csv | 47446 |  | 2017-11-01 → 2023-03-31 | No PM2.5 target column. |
| KA005.csv | 64272 |  | 2015-12-01 → 2023-03-31 | No PM2.5 target column. |
| KA006.csv | 64272 |  | 2015-12-01 → 2023-03-31 | No PM2.5 target column. |
