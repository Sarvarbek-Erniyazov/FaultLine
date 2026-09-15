# robots.txt fixtures

Both files are byte for byte as served, fetched with this project's own User-Agent
(`.gitattributes` marks this directory `-text`, so line endings stay as published).

| file | fetched from | server `Date` | bytes |
| --- | --- | --- | --- |
| `data_transportation_gov.txt` | `https://data.transportation.gov/robots.txt` | Tue, 15 Sep 2026 20:36:08 GMT | 1,754 |
| `www_nrc_gov.txt` | `https://www.nrc.gov/robots.txt` | Tue, 15 Sep 2026 20:34:24 GMT | 543 |

`data_transportation_gov.txt` separates `User-agent: *` from its `Disallow` rules with
blank lines; `www_nrc_gov.txt` writes its `User-agent: *` rules as full URLs and mixes
CRLF and LF line endings. `urllib.robotparser` reads both as allow-all for this project's
user agent; `faultline.download.robots` exists because of that.
