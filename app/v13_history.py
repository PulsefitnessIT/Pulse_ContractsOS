"""V13 pilot: evidence-backed, manually confirmed PPM visit history.

This module does not claim to interpret ambiguous service-planner marks or
synchronise with Sicon. Original contracts/Excel fields remain unchanged.
"""
import datetime as dt
import json
import re
import sqlite3
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from .store import connect, now
from .pilot_access import actor

router = APIRouter()
ALLOWED = {'Completed', 'Scheduled', 'Cancelled'}


def install(con):
    con.execute('''CREATE TABLE IF NOT EXISTS ppm_visits (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      contract_id INTEGER NOT NULL,
      visit_date TEXT NOT NULL,
      status TEXT NOT NULL CHECK(status IN ('Completed','Scheduled','Cancelled')),
      source_type TEXT NOT NULL,
      source_reference TEXT NOT NULL,
      notes TEXT NOT NULL DEFAULT '',
      reviewed_by TEXT NOT NULL,
      reviewed_at TEXT NOT NULL,
      FOREIGN KEY(contract_id) REFERENCES contracts(id),
      UNIQUE(contract_id,source_type,source_reference)
    )''')
    con.execute('CREATE INDEX IF NOT EXISTS idx_ppm_contract_date ON ppm_visits(contract_id,visit_date)')


class Visit(BaseModel):
    visit_date: str
    status: str
    source_type: str = Field(min_length=3, max_length=60)
    source_reference: str = Field(min_length=3, max_length=160)
    notes: str = Field(default='', max_length=2000)
    confirmed: bool = False


def validate(item):
    if not item.confirmed:
        raise HTTPException(400, 'A coordinator must confirm the source and visit status')
    if item.status not in ALLOWED:
        raise HTTPException(400, 'Unknown service visit status')
    try:
        date = dt.date.fromisoformat(item.visit_date)
    except ValueError:
        raise HTTPException(400, 'Visit date must be YYYY-MM-DD')
    if item.status == 'Completed' and date > dt.date.today():
        raise HTTPException(400, 'Cannot record a future date as completed')
    if item.source_type.strip().lower() in ('none', 'unknown'):
        raise HTTPException(400, 'Provide a traceable source type')
    return date


@router.post('/api/contracts/{cid}/ppm-visits')
def add_visit(cid: int, item: Visit):
    validate(item)
    con = connect()
    try:
        con.execute('BEGIN IMMEDIATE')
        install(con)
        if not con.execute('SELECT 1 FROM contracts WHERE id=?',(cid,)).fetchone():
            raise HTTPException(404,'Contract does not exist')
        try:
            cur=con.execute('''INSERT INTO ppm_visits
              (contract_id,visit_date,status,source_type,source_reference,notes,reviewed_by,reviewed_at)
              VALUES (?,?,?,?,?,?,?,?)''',(
                cid,item.visit_date,item.status,item.source_type.strip(),
                item.source_reference.strip(),item.notes.strip(),actor('Coordinator'),now()))
        except sqlite3.IntegrityError:
            raise HTTPException(409,'This source has already been attached to the contract')
        con.execute('''INSERT INTO changes(contract_id,actor,action,before_data,after_data,at)
                    VALUES(?,?,?,?,?,?)''',(cid,actor('Coordinator'),'PPM visit reviewed and recorded',
                None,json.dumps(item.model_dump(),ensure_ascii=False),now()))
        con.commit()
        return {'ok':True,'id':cur.lastrowid}
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


@router.get('/api/contracts/{cid}/ppm-visits')
def visit_history(cid: int, interval_months: int | None = None):
    if interval_months is not None and interval_months not in (1,2,3,4,6,12,18,24):
        raise HTTPException(400,'Select an explicitly verified maintenance interval')
    con=connect()
    try:
        install(con)
        if not con.execute('SELECT 1 FROM contracts WHERE id=?',(cid,)).fetchone():
            raise HTTPException(404,'Contract does not exist')
        visits=[dict(r) for r in con.execute('''SELECT * FROM ppm_visits WHERE contract_id=?
                    ORDER BY visit_date DESC,id DESC''',(cid,))]
    finally:
        con.close()
    completed=[x['visit_date'] for x in visits if x['status']=='Completed' and x['visit_date']<=dt.date.today().isoformat()]
    last=max(completed) if completed else None
    next_due=None
    if last and interval_months:
        from calendar import monthrange
        day=dt.date.fromisoformat(last)
        n=day.year*12+day.month-1+interval_months
        year,month=divmod(n,12)
        month+=1
        next_due=dt.date(year,month,min(day.day,monthrange(year,month)[1])).isoformat()
    return {'contract_id':cid,'visits':visits,'last_confirmed_service':last,
            'next_due':next_due,'verified_interval_months':interval_months,
            'disclaimer':'Next due uses the manually supplied verified interval, not an inferred contract entitlement.'}
