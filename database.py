import csv, logging, sqlite3
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd

log = logging.getLogger(__name__)

def connect(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    return con

def init_db(path):
    with connect(path) as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS stage1_annotations (
          id INTEGER PRIMARY KEY, subreddit TEXT NOT NULL, annotator_id TEXT NOT NULL,
          primary_category TEXT NOT NULL, second_choice TEXT NOT NULL, confidence INTEGER NOT NULL,
          ambiguity_flags TEXT NOT NULL, rationale TEXT, time_spent_seconds INTEGER NOT NULL,
          created_at TEXT NOT NULL, UNIQUE(subreddit, annotator_id));
        CREATE TABLE IF NOT EXISTS adjudications (
          subreddit TEXT PRIMARY KEY, label TEXT NOT NULL, rationale TEXT, adjudicator_id TEXT NOT NULL,
          created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS stage2_annotations (
          id INTEGER PRIMARY KEY, subreddit TEXT NOT NULL, annotator_id TEXT NOT NULL,
          label TEXT NOT NULL, confidence INTEGER NOT NULL, ambiguity_flags TEXT NOT NULL,
          rationale TEXT, time_spent_seconds INTEGER NOT NULL, created_at TEXT NOT NULL,
          UNIQUE(subreddit, annotator_id));''')

def now(): return datetime.now(timezone.utc).isoformat()
def completed(path, stage, annotator):
    table = "stage1_annotations" if stage == 1 else "stage2_annotations"
    with connect(path) as c: return {r[0] for r in c.execute(f"SELECT subreddit FROM {table} WHERE annotator_id=?", (annotator,))}
def save_stage1(path, values):
    with connect(path) as c:
        c.execute("""INSERT INTO stage1_annotations(subreddit,annotator_id,primary_category,second_choice,confidence,ambiguity_flags,rationale,time_spent_seconds,created_at) VALUES(?,?,?,?,?,?,?,?,?)""", values)
def save_stage2(path, values):
    with connect(path) as c:
        c.execute("""INSERT INTO stage2_annotations(subreddit,annotator_id,label,confidence,ambiguity_flags,rationale,time_spent_seconds,created_at) VALUES(?,?,?,?,?,?,?,?)""", values)
def save_adjudication(path, subreddit, label, rationale, adjudicator):
    with connect(path) as c: c.execute("INSERT OR REPLACE INTO adjudications VALUES(?,?,?,?,?)", (subreddit,label,rationale,adjudicator,now()))
def adjudicated_stock(path):
    with connect(path) as c: return {r[0] for r in c.execute("SELECT subreddit FROM adjudications WHERE label='stock_market'")}
def export_csv(path, outdir):
    outdir=Path(outdir); outdir.mkdir(parents=True, exist_ok=True)
    with connect(path) as c:
        for table in ("stage1_annotations","stage2_annotations","adjudications"):
            pd.read_sql_query(f"SELECT * FROM {table}", c).to_csv(outdir/f"{table}.csv", index=False)
