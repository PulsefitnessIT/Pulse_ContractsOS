# Security and data safety

The private GitHub repository holds code only. It is **not** storage for confidential Pulse Fitness customer data.

Do not commit:
- Customer names/addresses/contact details from business systems or site notes.
- Scanned invoices, account records, serial-number schedules or complete Maintenance Master workbooks containing real data.
- SQLite/MongoDB dumps, OCR text extracts or archive backups.
- API credentials, tokens, password files, production configuration or authentication cookies.

Use anonymised fixtures and environment variables for automated tests. Review any reference Excel template for actual customer records before including it.

## Minimum security for the independent pilot
- Keep PulseFitness.ai entirely disconnected and unchanged.
- Authenticate staff with simple pilot accounts and enforce role permissions in the backend.
- Record who changed each contract or approved an import; protect against concurrent stale edits.
- Require evidence-based review for uncertain handwritten contract data or financial values.
- Check upload types/sizes/paths; protect stored documents and log access appropriately.
- Keep backups encrypted and prove restoration, not just creation.
- Limit exported data to authorised records and test for PII exposure.
- Complete dependency and secrets scanning before deployment.
