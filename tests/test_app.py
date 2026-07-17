import pandas as pd
from prepare_data import prepare
import database as db
def test_sampling_and_short_report(tmp_path):
    csv=tmp_path/'subs.csv'; parquet=tmp_path/'posts.parquet'; out=tmp_path/'clean.parquet'
    pd.DataFrame({'subreddit':['r/a','b','c']}).to_csv(csv,index=False)
    rows=[{'subreddit':'a','title':f't{i}','selftext':'x','id':str(i)} for i in range(8)] + [{'subreddit':'b','title':'x','selftext':'x','id':'b'}]
    pd.DataFrame(rows).to_parquet(parquet)
    result,short=prepare(csv,parquet,out,7)
    assert result.subreddit.nunique()==1 and len(result)==8 and short==[('b',1),('c',0)]
def test_progress_duplicate_and_stage2(tmp_path):
    p=tmp_path/'a.sqlite3'; db.init_db(p)
    v=('a','one','stock_market','business',4,'','',3,db.now()); db.save_stage1(p,v)
    assert db.completed(p,1,'one')=={'a'}
    try: db.save_stage1(p,v); assert False
    except Exception: pass
    db.save_stage1(p,('a','two','stock_market','business',5,'','',4,db.now()))
    assert db.stage1_stock(p,'one')=={'a'}
    db.export_annotator_csv(p,tmp_path,'one')
    assert (tmp_path/'one_stage1.csv').exists() and (tmp_path/'one_stage2.csv').exists()
