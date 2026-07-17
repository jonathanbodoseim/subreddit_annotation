"""Create fixed Stage 1 (250) and Stage 2 (100 LLM-stock-market) queues."""
import argparse, re
from pathlib import Path
import pandas as pd
import pyarrow.parquet as pq
import pyarrow.dataset as ds
from config import SEED

def normalize_subreddit(value):
    s=str(value or "").strip().lower()
    return re.sub(r"^/?r/", "", s).strip().strip("/")
def first_column(df, candidates, label):
    for c in candidates:
        if c in df.columns: return c
    raise ValueError(f"Could not find {label}; tried {candidates}. Columns: {list(df.columns)}")
def prepare(subreddit_csv, submissions_parquet, output, seed=SEED, limit=250, stage2_limit=100):
    subs=pd.read_csv(subreddit_csv)
    subcol=first_column(subs,["subreddit","name","subreddit_name"],"subreddit column")
    subs["subreddit_normalized"]=subs[subcol].map(normalize_subreddit)
    all_names=sorted(set(subs.subreddit_normalized)-{""})
    available=set(pq.ParquetFile(submissions_parquet).schema.names)
    pcol=first_column(pd.DataFrame(columns=available),["subreddit","source_subreddit","subreddit_name"],"submission subreddit column")
    source=ds.dataset(submissions_parquet, format="parquet")
    counts=source.to_table(columns=["sample_type",pcol]).to_pandas()
    counts=counts[counts.sample_type.astype(str).str.lower().eq("submissions")]
    counts["subreddit_normalized"]=counts[pcol].map(normalize_subreddit)
    eligible=sorted(set(counts.loc[counts.groupby("subreddit_normalized")[pcol].transform("size")>=8,"subreddit_normalized"]) & set(all_names))
    stage1_names=pd.Series(eligible).sample(n=min(limit,len(eligible)),random_state=seed).tolist() if limit else eligible
    stock=set(subs.loc[subs.get("primary",pd.Series(index=subs.index)).astype(str).eq("stock_market"),"subreddit_normalized"]) if "primary" in subs else set()
    stock_eligible=sorted(stock & set(eligible))
    stage2_names=pd.Series(stock_eligible).sample(n=min(stage2_limit,len(stock_eligible)),random_state=seed+1).tolist() if stage2_limit else stock_eligible
    selected=set(stage1_names)|set(stage2_names)
    raw_by_norm=counts.groupby("subreddit_normalized")[pcol].first().to_dict()
    scan_names=[raw_by_norm[n] for n in selected]
    wanted=[c for c in ["subreddit","source_subreddit","subreddit_name","sample_type","title","submission_title","selftext","body","text","id","post_id","name"] if c in available]
    predicate=ds.field(pcol).isin(scan_names)
    if "sample_type" in available: predicate=predicate & (ds.field("sample_type")=="submissions")
    posts=source.to_table(columns=wanted,filter=predicate).to_pandas()
    title=first_column(posts,["title","submission_title"],"title column"); text=first_column(posts,["selftext","body","text"],"self-text column")
    posts["subreddit_normalized"]=posts[pcol].map(normalize_subreddit); posts["title_clean"]=posts[title].fillna("").astype(str).str.strip(); posts["selftext_clean"]=posts[text].fillna("").astype(str).str.strip()
    bad={"[deleted]","[removed]","deleted","removed","nan","none"}
    posts=posts[((~posts.title_clean.str.lower().isin(bad)) | (posts.selftext_clean.str.len()>0)) & ((posts.title_clean.str.len()>0)|(posts.selftext_clean.str.len()>0))]
    idcol=next((c for c in ["id","post_id","name"] if c in posts),None)
    posts=posts.drop_duplicates(idcol if idcol else ["subreddit_normalized","title_clean","selftext_clean"])
    rows=[]; short=[]
    for name in sorted(selected):
        group=posts[posts.subreddit_normalized==name]
        if len(group)<8: short.append((name,len(group))); continue
        for rank,(_,row) in enumerate(group.sample(n=8,random_state=seed).iterrows(),1):
            rows.append({"subreddit":name,"sample_rank":rank,"post_id":str(row[idcol]) if idcol else "","title":row.title_clean,"selftext":row.selftext_clean,"stage1_eligible":name in stage1_names,"stage2_eligible":name in stage2_names})
    result=pd.DataFrame(rows,columns=["subreddit","sample_rank","post_id","title","selftext","stage1_eligible","stage2_eligible"])
    Path(output).parent.mkdir(parents=True,exist_ok=True); result.to_parquet(output,index=False)
    print(f"Prepared Stage 1: {result.loc[result.stage1_eligible].subreddit.nunique()} subreddits; Stage 2: {result.loc[result.stage2_eligible].subreddit.nunique()} subreddits; {len(result)} submissions")
    if short: print("Fewer than eight usable submissions:", short)
    return result,short
if __name__=="__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--subreddits",required=True); ap.add_argument("--submissions",required=True); ap.add_argument("--output",required=True); ap.add_argument("--seed",type=int,default=SEED); ap.add_argument("--limit",type=int,default=250); ap.add_argument("--stage2-limit",type=int,default=100); a=ap.parse_args(); prepare(a.subreddits,a.submissions,a.output,a.seed,a.limit,a.stage2_limit)
