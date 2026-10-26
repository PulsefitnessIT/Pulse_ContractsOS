# Pulse Contracts OS × SmartQuote — Unified intake development

Development branch: feature/unified-smartquote-intake. Date: 26 October 2026.

## Implemented

- A coordinator-facing Accepted Quotes worklist in the existing Contracts OS PWA.
- A read-only, controlled accepted-quote handoff format named pulse.smartquote.accepted.v1.
- Preservation of legal customer/site, account/site refs, staged machine dates, serials, accepted equipment values and immutable PDF fingerprint evidence.
- Financial, quantity and date validation before creating an intake; no machine or contract changes.
- SHA256 idempotence for repeat imports. Different revised quote payloads remain separate records.
- Exact contract reference or Sage-account-plus-Sicon-site reference matching only; no name-only automatic link.
- Explicit linkage to an existing contract with audit note, never an automatic overwrite.
- Coordinator exception queue for missing account/site refs, archived quote PDF evidence, approved prices, serials and coverage dates.
- Additive runtime SQLite tables. Original Maintenance Master, contract/equipment register, quotes and audit information remain unchanged.

## Pilot coordinator flow

1. Confirm the quote was marked Accepted and preserve its approved PDF snapshot in SmartQuote.
2. Export the standard handoff JSON from that accepted snapshot.
3. Choose Accepted quotes in Contracts OS and check the handoff JSON.
4. Review exceptions and verified existing-contract candidates in one place.
5. Add to the worklist once; the same revision cannot be accidentally imported twice.
6. Link to an existing agreement only after confirming account/site or contract identifiers.

## Release restrictions

No Sage/Sicon write-back, no equipment activation and no automated invoice creation.
The current handoff is a controlled pilot, not approved Sicon import. Managers must approve
the price/cover policy and test mapping in Sicon before any production handover.
Private runtime databases, contracts and documents must never be committed to GitHub.
PulseFitness.ai and main/develop branches remain unchanged.

## Tests

Python compileall plus fictional-data tests in tests/test_pilot_data_smartquote_intake.py.

## Next

Connect accepted quote snapshots directly using authenticated HTTPS, add Contract Setup Cases
and produce two validated exports with an auditable Sicon reference and staged activation plan.