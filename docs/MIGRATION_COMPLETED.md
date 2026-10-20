# Source migration record

- The source-only V13 PWA ZIP was inspected before import.
- No database, populated Excel Master, customer contact list, original invoices or uploads were imported.
- Unused manually transcribed real customer examples in `app/main.py` were removed.
- Tests and documentation use fictionalised customer/site and invoice identifiers.
- Existing Python regression checks need a disposable test fixture; not a production-data release.
- Old release notes are in `docs/archive` and do not need to be shipped to employee computers.
- Windows `.bat` files are retained for developer/local-pilot support; the staff PWA does not require them.
- Branch is a development migration and must be reviewed before merging to `develop`.
