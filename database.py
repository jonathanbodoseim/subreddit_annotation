"""Small storage adapter: SQLite locally, PostgreSQL/Supabase in the cloud."""
import logging, os, sqlite3, threading
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd

log = logging.getLogger(__name__)
_pools={}
_pool_lock=threading.Lock()

def database_url(path=None):
    if path and str(path).startswith(("postgresql://", "postgres://")): return str(path)
    url=os.getenv("DATABASE_URL")
    if url: return url
    try:
        import streamlit as st
        return st.secrets.get("DATABASE_URL")
    except Exception:
        return None

def is_postgres(path=None): return bool(database_url(path))

def _postgres_pool(url):
    with _pool_lock:
        if url not in _pools:
            from psycopg2.pool import ThreadedConnectionPool
            _pools[url]=ThreadedConnectionPool(1,5,url,sslmode="require",connect_timeout=10)
        return _pools[url]

@contextmanager
def connect(path):
    url=database_url(path)
    if url:
        pool=_postgres_pool(url)
        con=pool.getconn()
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            pool.putconn(con)
        return
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    con=sqlite3.connect(path, timeout=30, check_same_thread=False)
    con.row_factory=sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

def execute(c, query, params=()):
    if c.__class__.__module__.startswith("psycopg2"):
        cursor=c.cursor()
        cursor.execute(query.replace("?", "%s"),params)
        return cursor
    return c.execute(query,params)

SCHEMA='''CREATE TABLE IF NOT EXISTS stage1_annotations (
 id INTEGER PRIMARY KEY, subreddit TEXT NOT NULL, annotator_id TEXT NOT NULL,
 primary_category TEXT NOT NULL, second_choice TEXT NOT NULL, confidence INTEGER NOT NULL,
 ambiguity_flags TEXT NOT NULL, rationale TEXT, time_spent_seconds INTEGER NOT NULL,
 created_at TEXT NOT NULL, UNIQUE(subreddit, annotator_id));
CREATE TABLE IF NOT EXISTS stage2_annotations (
 id INTEGER PRIMARY KEY, subreddit TEXT NOT NULL, annotator_id TEXT NOT NULL,
 label TEXT NOT NULL, confidence INTEGER NOT NULL, ambiguity_flags TEXT NOT NULL,
 rationale TEXT, time_spent_seconds INTEGER NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(subreddit, annotator_id));'''

def init_db(path):
    with connect(path) as c:
        if is_postgres(path):
            for statement in SCHEMA.replace("id INTEGER PRIMARY KEY", "id SERIAL PRIMARY KEY").split(";"):
                if statement.strip(): execute(c, statement)
        else: c.executescript(SCHEMA)

def now(): return datetime.now(timezone.utc).isoformat()
def completed(path, stage, annotator):
    table="stage1_annotations" if stage==1 else "stage2_annotations"
    with connect(path) as c: return {r[0] for r in execute(c,f"SELECT subreddit FROM {table} WHERE annotator_id=?",(annotator,))}
def save_stage1(path, values):
    with connect(path) as c: execute(c,"""INSERT INTO stage1_annotations(subreddit,annotator_id,primary_category,second_choice,confidence,ambiguity_flags,rationale,time_spent_seconds,created_at) VALUES(?,?,?,?,?,?,?,?,?)
      ON CONFLICT(subreddit,annotator_id) DO UPDATE SET primary_category=excluded.primary_category,second_choice=excluded.second_choice,confidence=excluded.confidence,ambiguity_flags=excluded.ambiguity_flags,rationale=excluded.rationale,time_spent_seconds=excluded.time_spent_seconds,created_at=excluded.created_at""",values)
def save_stage2(path, values):
    with connect(path) as c: execute(c,"""INSERT INTO stage2_annotations(subreddit,annotator_id,label,confidence,ambiguity_flags,rationale,time_spent_seconds,created_at) VALUES(?,?,?,?,?,?,?,?)
      ON CONFLICT(subreddit,annotator_id) DO UPDATE SET label=excluded.label,confidence=excluded.confidence,ambiguity_flags=excluded.ambiguity_flags,rationale=excluded.rationale,time_spent_seconds=excluded.time_spent_seconds,created_at=excluded.created_at""",values)
def get_annotation(path, stage, annotator, subreddit):
    table="stage1_annotations" if stage==1 else "stage2_annotations"
    label="primary_category" if stage==1 else "label"
    with connect(path) as c:
        row=execute(c,f"SELECT {label},confidence FROM {table} WHERE annotator_id=? AND subreddit=?",(annotator,subreddit)).fetchone()
    return {"label":row[0],"confidence":row[1]} if row else None
def stage1_stock(path, annotator):
    with connect(path) as c: return {r[0] for r in execute(c,"SELECT subreddit FROM stage1_annotations WHERE annotator_id=? AND primary_category='stock_market'",(annotator,))}
def export_annotator_csv(path, outdir, annotator):
    outdir=Path(outdir); outdir.mkdir(parents=True,exist_ok=True)
    with connect(path) as c:
        ph="%s" if is_postgres(path) else "?"
        for table,stage in (("stage1_annotations","stage1"),("stage2_annotations","stage2")):
            pd.read_sql_query(f"SELECT * FROM {table} WHERE annotator_id = {ph}",c,params=(annotator,)).to_csv(outdir/f"{annotator}_{stage}.csv",index=False)
