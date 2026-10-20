# V11 test results

The following tests were executed against the standalone V11 source with no live PulseFitness.ai or Sage/Sicon connection.

| Test | Result | Evidence |
|---|---|---|
| V11 Excel capacity expansion | PASS | Beyond-template rows in all five working registers; filters extended; original eight tabs and report XML preserved |
| New-row calculations/styles | PASS | Formula in Maintenance Database L804 and styled 37-column row |
| Dropdown/validation beyond row 2,495 | PASS | Validations extended through row 2,500 |
| V11 invoice scorecard | PASS | Correct, corrected and manually identified entries; CSV injection protection |
| V10 independent pilot concurrency | PASS | One of two stale simultaneous edits rejected (HTTP 409); invoice/weekly data protected |
| V4 prior export/roundtrip | PASS | Conflict approval, history, Excel roundtrip and backups |
| V5 import and historical contract transfer | PASS | New Excel records and historical transfer preserved |
| V6 printed invoice OCR safety | PASS | Source evidence produced; uncertain document fields not auto-approved |
| V7 contract matching | PASS | Contradictory site and shared account matches not silently approved |
| V8 invoice review | PASS | Confirmation/history for real source-page fields |
| V9 batch and review queue | PASS | Batch upload and queue testing |

Additional legacy smoke, V2 and V3 suites passed during the development run. An initial sweep reported failures in several legacy suites only because the API version string was changed to `1.1.0`; keeping the previous API compatibility string and adding separate `release: V11` resolved those failures. Targeted re-runs subsequently passed.

## Still unverified
- Docker image has **not** been built or deployed in the target IT environment.
- Network access, reverse-proxy HTTPS, password resets, offsite backup and restoration have not been validated on the organisation's infrastructure.
- Microsoft Excel desktop acceptance remains required; OOXML structural checks do not prove desktop UI or print behaviour.
- Invoice extraction accuracy from a larger, representative invoice set has not yet been established.
