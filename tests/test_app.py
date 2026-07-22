import sqlite3
import pandas as pd
from prepare_data import prepare
import database as db

class FakePostgresConnection:
    __module__="psycopg2.extensions"
    def __init__(self): self.cursor_instance=FakeCursor()
    def cursor(self): return self.cursor_instance
class FakeCursor:
    def execute(self,query,params): self.called=(query,params)

def test_postgres_execute_uses_cursor():
    connection=FakePostgresConnection()
    cursor=db.execute(connection,"SELECT ?",("value",))
    assert cursor is connection.cursor_instance
    assert cursor.called==("SELECT %s",("value",))
def test_sampling_and_short_report(tmp_path):
    csv=tmp_path/'subs.csv'; parquet=tmp_path/'posts.parquet'; out=tmp_path/'clean.parquet'
    pd.DataFrame({'subreddit':['r/a','b','c']}).to_csv(csv,index=False)
    rows=[{'subreddit':'a','title':f't{i}','selftext':'x','id':str(i)} for i in range(8)] + [{'subreddit':'b','title':'x','selftext':'x','id':'b'}]
    pd.DataFrame(rows).to_parquet(parquet)
    result,short=prepare(csv,parquet,out,7)
    assert result.subreddit.nunique()==1 and len(result)==8 and short==[('b',1),('c',0)]
def test_progress_update_and_stage2(tmp_path):
    p=tmp_path/'a.sqlite3'; db.init_db(p)
    v=('a','one','stock_market','business',4,'','',3,db.now()); db.save_stage1(p,v)
    assert db.completed(p,1,'one')=={'a'}
    updated=('a','one','crypto','',2,'','',5,db.now()); db.save_stage1(p,updated)
    assert db.get_annotation(p,1,'one','a')["label"]=='crypto'
    db.save_stage1(p,('a','two','stock_market','business',5,'','',4,db.now()))
    assert db.stage1_stock(p,'one')==set()
    assert db.stage1_stock(p,'two')=={'a'}
    db.export_annotator_csv(p,tmp_path,'one')
    assert (tmp_path/'one_stage1.csv').exists() and (tmp_path/'one_stage2.csv').exists()

def test_stage2_four_category_migration_archives_and_resets_once(tmp_path):
    p=tmp_path/'migration.sqlite3'; db.init_db(p)
    with sqlite3.connect(p) as c:
        c.execute("DELETE FROM app_migrations WHERE name=?",(db.STAGE2_FOUR_CATEGORY_MIGRATION,))
    db.save_stage2(p,('a','one','residual',3,'','',2,db.now()))
    db.init_db(p)
    assert db.completed(p,2,'one')==set()
    with sqlite3.connect(p) as c:
        assert c.execute("SELECT label FROM stage2_annotations_archive_20260722").fetchall()==[('residual',)]
    db.init_db(p)
    with sqlite3.connect(p) as c:
        assert c.execute("SELECT COUNT(*) FROM stage2_annotations_archive_20260722").fetchone()[0]==1
