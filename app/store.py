"""SQLite persistence, bootstrap from the approved 8-tab Maintenance Master."""
from __future__ import annotations
import os,json,sqlite3,datetime as dt,collections,datetime,uuid
from pathlib import Path
from .excel_io import ExcelSource,REGISTER_SHEETS

BASE=os.path.dirname(os.path.dirname(__file__))
DATA=os.environ.get('PULSE_DATA_DIR',os.path.join(BASE,'data'))
DB=os.path.join(DATA,'contracts.sqlite3')
TEMPLATE=os.path.join(DATA,'approved_master.xlsx')

def connect():
    con=sqlite3.connect(DB,timeout=15)
    con.row_factory=sqlite3.Row
    con.execute('PRAGMA journal_mode=WAL')
    con.execute('PRAGMA foreign_keys=ON')
    return con

def now():return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')

def init_db():
    os.makedirs(DATA,exist_ok=True)
    con=connect()
    con.executescript('''
    CREATE TABLE IF NOT EXISTS contracts (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      row_key TEXT NOT NULL UNIQUE,
      status TEXT NOT NULL DEFAULT 'Active',
      source_sheet TEXT NOT NULL,
      source_row INTEGER NOT NULL,
      old_sheet TEXT DEFAULT '', old_row INTEGER,
      fields TEXT NOT NULL, fill TEXT DEFAULT '', dirty INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_contract_sheet ON contracts(status,source_sheet);
    CREATE TABLE IF NOT EXISTS ledger (
      id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL,
      source_row INTEGER, fields TEXT NOT NULL, dirty INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS changes (
      id INTEGER PRIMARY KEY AUTOINCREMENT, contract_id INTEGER,
      actor TEXT NOT NULL, action TEXT NOT NULL, before_data TEXT,
      after_data TEXT, at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS imports (
      id INTEGER PRIMARY KEY AUTOINCREMENT, filename TEXT NOT NULL, type TEXT NOT NULL,
      sha256 TEXT NOT NULL, status TEXT NOT NULL, extraction_note TEXT NOT NULL,
      proposals TEXT NOT NULL, created_at TEXT NOT NULL
    );
    CREATE UNIQUE INDEX IF NOT EXISTS import_hash ON imports(sha256);
    CREATE TABLE IF NOT EXISTS catalogue (
      sku TEXT PRIMARY KEY, model TEXT, name TEXT, grp TEXT, description TEXT,
      category TEXT, manufacturer TEXT, frame TEXT, upholstery TEXT,
      console TEXT, software TEXT, range_name TEXT, status TEXT, warranty_catalogue TEXT
    );
    CREATE TABLE IF NOT EXISTS equipment (
      id INTEGER PRIMARY KEY AUTOINCREMENT, contract_id INTEGER NOT NULL,
      sku TEXT NOT NULL, serial_number TEXT DEFAULT '', quantity INTEGER NOT NULL DEFAULT 1,
      installation_date TEXT DEFAULT '', warranty_expiry TEXT DEFAULT '',
      invoice_reference TEXT DEFAULT '', notes TEXT DEFAULT '',
      created_at TEXT NOT NULL,
      FOREIGN KEY(contract_id) REFERENCES contracts(id)
    );
    CREATE INDEX IF NOT EXISTS idx_equipment_contract ON equipment(contract_id);
    ''')
    # Seed a compact, read-only product catalogue, separate from contractual records.
    catalogue_path=Path(DATA)/'equipment_catalogue.json'
    if catalogue_path.exists() and con.execute('SELECT COUNT(*) FROM catalogue').fetchone()[0]==0:
        catalogue=json.loads(catalogue_path.read_text(encoding='utf-8'))
        con.executemany('''INSERT OR IGNORE INTO catalogue
          (sku,model,name,grp,description,category,manufacturer,frame,upholstery,console,software,range_name,status,warranty_catalogue)
          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',[(r.get('sku',''),r.get('model',''),r.get('name',''),r.get('group',''),r.get('description',''),r.get('category',''),r.get('manufacturer',''),r.get('frame',''),r.get('upholstery',''),r.get('console',''),r.get('software',''),r.get('range',''),r.get('status',''),r.get('warranty_catalogue','')) for r in catalogue])
        con.commit()
    # V4: row revision tokens and a reproducible export snapshot history.
    contract_columns={r[1] for r in con.execute('PRAGMA table_info(contracts)')}
    if 'revision' not in contract_columns:
        con.execute('ALTER TABLE contracts ADD COLUMN revision INTEGER NOT NULL DEFAULT 1')
    con.execute('''CREATE TABLE IF NOT EXISTS export_snapshots (
       export_id TEXT PRIMARY KEY, exported_at TEXT NOT NULL,
       baseline_json TEXT NOT NULL, file_sha256 TEXT NOT NULL DEFAULT ''
    )''')
    con.execute('''CREATE TABLE IF NOT EXISTS renewal_history (
       id INTEGER PRIMARY KEY AUTOINCREMENT, contract_id INTEGER NOT NULL,
       old_start TEXT, old_expiry TEXT, old_amount TEXT, new_start TEXT,
       new_expiry TEXT, new_amount TEXT, effective_at TEXT NOT NULL, actor TEXT NOT NULL,
       FOREIGN KEY(contract_id) REFERENCES contracts(id)
    )''')
    con.execute('''CREATE TABLE IF NOT EXISTS import_reviews (
       review_id TEXT PRIMARY KEY, export_id TEXT NOT NULL,
       created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
       rows_json TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Pending',
       FOREIGN KEY(export_id) REFERENCES export_snapshots(export_id)
    )''')
    # V8: verified invoice *evidence*, separate from financial reporting and contracts.
    # It is unsafe to book equipment sales as recurring service-contract income.
    con.execute('''CREATE TABLE IF NOT EXISTS invoice_document_reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        import_id INTEGER NOT NULL,
        group_id TEXT NOT NULL,
        review_data TEXT NOT NULL,
        verified_at TEXT NOT NULL,
        UNIQUE(import_id,group_id),
        FOREIGN KEY(import_id) REFERENCES imports(id)
    )''')
    con.execute('''CREATE TABLE IF NOT EXISTS invoice_review_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        import_id INTEGER NOT NULL, group_id TEXT NOT NULL,
        before_data TEXT, after_data TEXT NOT NULL, reviewed_at TEXT NOT NULL
    )''')
    # V12: service dates remain proposals until verified; sourced contact records are distinct from workbook fields.
    con.execute('''CREATE TABLE IF NOT EXISTS service_planner_approvals (
         source_row INTEGER PRIMARY KEY, contract_id INTEGER NOT NULL,
         date_recorded TEXT NOT NULL, source_details TEXT NOT NULL,
         applied_at TEXT NOT NULL, actor TEXT NOT NULL,
         FOREIGN KEY(contract_id) REFERENCES contracts(id))''')
    con.execute('''CREATE TABLE IF NOT EXISTS site_contact_research (
         contract_id INTEGER PRIMARY KEY, phone TEXT DEFAULT '', email TEXT DEFAULT '',
         website TEXT DEFAULT '', source_url TEXT DEFAULT '', contact_name TEXT DEFAULT '',
         verified_at TEXT NOT NULL, actor TEXT NOT NULL,
         FOREIGN KEY(contract_id) REFERENCES contracts(id))''')
    # Schema migrations are additive, so existing V2 pilot records are retained.
    import_columns={r[1] for r in con.execute('PRAGMA table_info(imports)')}
    if 'evidence_json' not in import_columns:
        con.execute("ALTER TABLE imports ADD COLUMN evidence_json TEXT NOT NULL DEFAULT '{}'")
    equipment_columns={r[1] for r in con.execute('PRAGMA table_info(equipment)')}
    if 'source_import_id' not in equipment_columns:
        con.execute('ALTER TABLE equipment ADD COLUMN source_import_id INTEGER')
    ledger_columns={r[1] for r in con.execute('PRAGMA table_info(ledger)')}
    if 'dirty' not in ledger_columns: con.execute('ALTER TABLE ledger ADD COLUMN dirty INTEGER NOT NULL DEFAULT 0')
    if 'revision' not in ledger_columns: con.execute('ALTER TABLE ledger ADD COLUMN revision INTEGER NOT NULL DEFAULT 1')
    count=con.execute('SELECT count(*) FROM contracts').fetchone()[0]
    if count==0:
        src=ExcelSource(TEMPLATE)
        for sheet in REGISTER_SHEETS:
            headers,rows=src.records(sheet)
            for item in rows:
                obj=item['fields']
                # Read only actual site records, not preformatted unused rows.
                site=str(obj.get('Customer / site','') or '').strip()
                if not site:continue
                key=str(obj.get('Record ID') or f'{sheet}-{item["row"]}')
                con.execute('INSERT INTO contracts(row_key,status,source_sheet,source_row,fields,fill,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)',
                    (key,'Active' if sheet=='Maintenance Database' else 'Expired',sheet,item['row'],json.dumps(obj,ensure_ascii=False),item['fill'],now(),now()))
        for sheet in ('Weekly Values','Invoices','Quotes'):
            hdr,rows=src.records(sheet)
            batch=[(sheet,item['row'],json.dumps(item['fields'],ensure_ascii=False)) for item in rows]
            con.executemany('INSERT INTO ledger(kind,source_row,fields) VALUES (?,?,?)',batch)
        src.z.close()
        con.commit()
    con.close()

def parse_row(row,summary=False):
    if not row:return None
    fields=json.loads(row['fields'])
    output={'id':row['id'],'row_key':row['row_key'],'status':row['status'],'source_sheet':row['source_sheet'],'fill':row['fill'],'updated_at':row['updated_at'],'revision':row['revision']}
    if not summary:output['fields']=fields
    else:
        keys=('Customer / site','Contract number','Contract / warranty type','Invoice Code','Start date','Expiry date','Contract amount (£)','Sales region','Sales manager','Contract coordinator','Renewal status','Sage Checked and Updated','Site notes')
        output['fields']={k:fields.get(k,'') for k in keys}
    return output

def status_for(date):
    if not date:return 'Date missing'
    try:delta=(dt.date.fromisoformat(date[:10])-dt.date.today()).days
    except ValueError:return 'Date needs checking'
    if delta<0:return 'Expiry passed – check'
    if delta<=30:return 'Due within 30 days'
    if delta<=60:return 'Due in 31–60 days'
    if delta<=90:return 'Due in 61–90 days'
    return 'Over 90 days'

def type_bucket(text):
    t=str(text or '').lower()
    if 'charge' in t or 'reactive' in t:return 'Chargeable'
    if any(x in t for x in ('warr','gold','platinum','silver')):return 'Warranty'
    if any(x in t for x in ('contract','maintenance','type a','type b','type c')):return 'Contract'
    return 'Other / unclear'

def stats():
    con=connect();active=con.execute('SELECT fields FROM contracts WHERE status="Active"').fetchall()
    exp=con.execute('SELECT count(*) FROM contracts WHERE status="Expired"').fetchone()[0]
    types=collections.Counter();statuses=collections.Counter();sales=collections.Counter();mgrs=set();regions=set()
    for r in active:
        f=json.loads(r['fields']);types[type_bucket(f.get('Contract / warranty type'))]+=1
        statuses[status_for(str(f.get('Expiry date','') or ''))]+=1
        mgr=str(f.get('Sales manager') or '').strip()
        if mgr:mgrs.add(mgr)
        reg=str(f.get('Sales region') or '').strip()
        if reg:regions.add(reg)
    inv=con.execute('SELECT fields FROM ledger WHERE kind="Invoices"').fetchall()
    inv2026=collections.defaultdict(float)
    for x in inv:
        f=json.loads(x['fields']);mon=str(f.get('Invoice month') or '')[:7]
        try:val=float(f.get('Amount ex VAT (£)') or 0)
        except (ValueError,TypeError):val=0
        if mon:inv2026[mon]+=val
    con.close()
    return {'active':len(active),'expired':exp,'types':types,'renewals':statuses,'sales_managers':sorted(mgrs),'regions':sorted(regions),'monthly_invoices':dict(sorted(inv2026.items()))}
