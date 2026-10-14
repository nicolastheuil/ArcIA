"""Owner records and encrypted sessions; never open OmniRoute's database."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import threading
import time
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class Store:
    def __init__(self,path,key):
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(path,check_same_thread=False)
        self.db.row_factory=sqlite3.Row;self.lock=threading.RLock()
        self.cipher=AESGCM(hashlib.sha256(key).digest())
        self.db.executescript('''
          PRAGMA journal_mode=WAL;
          CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY CHECK(id=1),value TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS connections(id TEXT PRIMARY KEY,issuer TEXT NOT NULL,subject TEXT NOT NULL,
            provider TEXT NOT NULL,label TEXT NOT NULL,native_name TEXT NOT NULL UNIQUE,native_id TEXT,phase TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,value BLOB NOT NULL,expires REAL NOT NULL);
          CREATE TABLE IF NOT EXISTS credentials(owner TEXT PRIMARY KEY,native_id TEXT,value BLOB NOT NULL);
          CREATE TABLE IF NOT EXISTS preferences(owner TEXT PRIMARY KEY,enabled INTEGER NOT NULL CHECK(enabled IN (0,1)));
        ''');self.db.commit()

    def seal(self,value,context):
        nonce=os.urandom(12)
        return nonce+self.cipher.encrypt(nonce,json.dumps(value).encode(),context.encode())

    def open(self,value,context):return json.loads(self.cipher.decrypt(value[:12],value[12:],context.encode()))

    def settings(self):
        with self.lock:row=self.db.execute('SELECT value FROM settings WHERE id=1').fetchone()
        return json.loads(row[0]) if row else {'personal_providers_enabled':False,'automatic_mode':'auto/smart',
            'enterprise_connections':[],'allowed_models':[],'personal_providers':['openai','anthropic','gemini','openrouter']}

    def save_settings(self,value):
        with self.lock,self.db:self.db.execute('INSERT INTO settings VALUES(1,?) ON CONFLICT(id) DO UPDATE SET value=excluded.value',(json.dumps(value),))

    def session(self,identifier,value=None):
        digest=hashlib.sha256(identifier.encode()).hexdigest()
        with self.lock,self.db:
            self.db.execute('DELETE FROM sessions WHERE expires < ?',(time.time(),))
            if value is not None:
                if (not self.db.execute('SELECT 1 FROM sessions WHERE id=?',(digest,)).fetchone()
                    and self.db.execute('SELECT count(*) FROM sessions').fetchone()[0]>=1024):
                    raise ValueError('SESSION_CAPACITY')
                self.db.execute('INSERT OR REPLACE INTO sessions VALUES(?,?,?)',
                    (digest,self.seal(value,digest),min(value['created']+28800,time.time()+1800)))
            row=self.db.execute('SELECT value FROM sessions WHERE id=?',(digest,)).fetchone()
        if not row:raise PermissionError('LOGIN_REQUIRED')
        return self.open(row[0],digest)

    def logout(self,identifier):
        with self.lock,self.db:self.db.execute('DELETE FROM sessions WHERE id=?',(hashlib.sha256(identifier.encode()).hexdigest(),))

    def connections(self,issuer=None,subject=None):
        with self.lock:
            rows=self.db.execute('SELECT * FROM connections'+(' WHERE issuer=? AND subject=?' if issuer else ''),
                (issuer,subject) if issuer else ()).fetchall()
        return [dict(row) for row in rows]

    def reserve(self,value):
        with self.lock,self.db:self.db.execute('INSERT INTO connections VALUES(?,?,?,?,?,?,NULL,?)',
            tuple(value[k] for k in ('id','issuer','subject','provider','label','native_name'))+('pending',))

    def update(self,identifier,native_id,phase):
        with self.lock,self.db:self.db.execute('UPDATE connections SET native_id=?,phase=? WHERE id=?',(native_id,phase,identifier))

    def remove(self,identifier):
        with self.lock,self.db:self.db.execute('DELETE FROM connections WHERE id=?',(identifier,))

    def credential(self,owner,value=None):
        with self.lock,self.db:
            if value is not None:self.db.execute('INSERT OR REPLACE INTO credentials VALUES(?,?,?)',
                (owner,value['id'],self.seal(value,owner)))
            row=self.db.execute('SELECT value FROM credentials WHERE owner=?',(owner,)).fetchone()
        return self.open(row[0],owner) if row else None

    def preference(self,owner,enabled=None):
        with self.lock,self.db:
            if enabled is not None:self.db.execute('INSERT OR REPLACE INTO preferences VALUES(?,?)',(owner,int(enabled)))
            row=self.db.execute('SELECT enabled FROM preferences WHERE owner=?',(owner,)).fetchone()
        return bool(row[0]) if row else False

    def forget_credential(self,owner):
        with self.lock,self.db:self.db.execute('DELETE FROM credentials WHERE owner=?',(owner,))
