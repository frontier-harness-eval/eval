"""Atomic, resume-safe conservative API-equivalent stage budget (not billing)."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def ledger_paths(local, protocol):
    """Explicit new authorizations use independent ledgers; history is immutable."""
    name = protocol.get('budget_ledger', 'stage-ledger')
    if not isinstance(name, str) or not name or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-_' for c in name):
        raise ValueError('Invalid budget ledger name')
    return Path(local)/(name+'.sqlite'), Path(local)/(name+'.json')


class Ledger:
    def __init__(self, path, ceiling_usd=250):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, isolation_level=None, timeout=30)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS entries (id TEXT PRIMARY KEY, status TEXT NOT NULL, reserved INTEGER NOT NULL, charged INTEGER NOT NULL DEFAULT 0, note TEXT NOT NULL, updated TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS reconciliations (id INTEGER PRIMARY KEY, run_id TEXT NOT NULL, prior_charge INTEGER NOT NULL, measured_charge INTEGER NOT NULL, evidence TEXT NOT NULL, updated TEXT NOT NULL)')
        self.ceiling = round(ceiling_usd * 1_000_000)

    def reserve(self, run_id, usd, note=''):
        amount = round(usd * 1_000_000)
        if amount <= 0:
            raise ValueError('positive reservation required')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            if self.db.execute('SELECT 1 FROM entries WHERE id=?', (run_id,)).fetchone():
                raise ValueError('existing run must be reconciled, never redispatched')
            used = self.db.execute('SELECT COALESCE(SUM(charged + reserved),0) FROM entries').fetchone()[0]
            if used + amount > self.ceiling:
                raise ValueError('stage ceiling: dispatch refused')
            self.db.execute('INSERT INTO entries VALUES (?, ?, ?, 0, ?, ?)', (run_id, 'reserved', amount, note, datetime.now(timezone.utc).isoformat()))
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    def settle(self, run_id, usd, note='', uncertain=False):
        amount = round(usd * 1_000_000)
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row = self.db.execute('SELECT reserved,status FROM entries WHERE id=?', (run_id,)).fetchone()
            if not row or row[1] != 'reserved':
                raise ValueError('not an outstanding reservation')
            if amount < 0 or amount > row[0]:
                raise ValueError('outside reserved envelope; stop and reconcile')
            # Missing/incomplete usage keeps the full reservation charged. No
            # zero-spend assumption after a dispatch marker or crash.
            charge = row[0] if uncertain else amount
            self.db.execute('UPDATE entries SET status=?,reserved=0,charged=?,note=?,updated=? WHERE id=?', ('uncertain' if uncertain else 'settled', charge, note, datetime.now(timezone.utc).isoformat(), run_id))
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    def snapshot(self):
        rows = [dict(zip(('run_id','status','reserved_micros','charged_micros','note','updated'), r)) for r in self.db.execute('SELECT * FROM entries ORDER BY updated,id')]
        charged = sum(r['charged_micros'] for r in rows)
        reserved = sum(r['reserved_micros'] for r in rows)
        reconciliations=[dict(zip(('id','run_id','prior_charge_micros','measured_charge_micros','evidence','updated'),r)) for r in self.db.execute('SELECT * FROM reconciliations ORDER BY id')]
        return dict(basis='conservative API-equivalent; subscription, not credits billing', ceiling_usd=self.ceiling/1e6, charged_usd=charged/1e6, reserved_usd=reserved/1e6, remaining_usd=(self.ceiling-charged-reserved)/1e6, entries=rows,reconciliations=reconciliations)

    def reconcile(self,run_id,usd,evidence):
        amount=round(usd*1e6)
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row=self.db.execute('SELECT charged,status FROM entries WHERE id=?',(run_id,)).fetchone()
            if not row or row[1]!='uncertain' or amount<0 or amount>row[0] or not evidence:
                raise ValueError('only previously held uncertain usage with explicit evidence can be reconciled')
            now=datetime.now(timezone.utc).isoformat()
            self.db.execute('INSERT INTO reconciliations(run_id,prior_charge,measured_charge,evidence,updated) VALUES (?,?,?,?,?)',(run_id,row[0],amount,evidence,now))
            self.db.execute('UPDATE entries SET status="settled",charged=?,note=?,updated=? WHERE id=?',(amount,evidence,now,run_id))
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK');raise

    def export(self, path):
        Path(path).write_text(json.dumps(self.snapshot(), indent=2)+'\n')
