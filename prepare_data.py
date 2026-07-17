"""Prepare a reproducible eight-submission-per-subreddit annotation dataset."""
import argparse, logging, re
from pathlib import Path
import pandas as pd
import pyarrow.parquet as pq
import pyarrow.dataset as ds
from config import SEED

log=logging.getLogger(__name__)
def normalize_subreddit(value):
    s=str(value or "").strip().lower()
    s=re.sub(r"^/?r/", "", s).strip().strip("/")
    return s
def first_column(df, candidates, label):
    for c in candidates:
        if c in df.columns: return c
    raise ValueError(f"Could not find {label}; tried {candidates}. Columns: {list(df.columns)}")
def prepare(subreddit_csv, submissions_parquet, output, seed=SEED, limit=250):
    subs=pd.read_csv(subreddit_csv)
    subcol=first_column(subs,["subreddit","name","subreddit_name"],"subreddit column")
    names=sorted({normalize_subreddit(x) for x in subs[subcol] if normalize_subreddit(x)})
    if limit and len(names)>limit:
        names=pd.Series(names).sample(n=limit, random_state=seed).sort_values().tolist()
    # The source can be very large; avoid materializing unrelated columns.
    available=set(pq.ParquetFile(submissions_parquet).schema.names)
    pcol=next((c for c in ["subreddit","source_subreddit","subreddit_name"] if c in available), None)
    if not pcol: raise ValueError(f"Could not find submission subreddit column; columns: {sorted(available)}")
    wanted=[c for c in ["subreddit","source_subreddit","subreddit_name","sample_type","title","submission_title","selftext","body","text","id","post_id","name"] if c in available]
    source=ds.dataset(submissions_parquet, format="parquet")
    predicate=(ds.field("sample_type") == "submissions") if "sample_type" in available else None
    name_filter=ds.field(pcol).isin(names)
    predicate=name_filter if predicate is None else predicate & name_filter
    posts=source.to_table(columns=wanted, filter=predicate).to_pandas()
    pcol=first_column(posts,["subreddit","source_subreddit","subreddit_name"],"submission subreddit column")
    title=first_column(posts,["title","submission_title"],"title column")
    text=first_column(posts,["selftext","body","text"],"self-text column")
    posts=posts.copy(); posts["subreddit_normalized"]=posts[pcol].map(normalize_subreddit)
    posts["title_clean"]=posts[title].fillna("").astype(str).str.strip()
    posts["selftext_clean"]=posts[text].fillna("").astype(str).str.strip()
    bad={"[deleted]","[removed]","deleted","removed","nan","none"}
    posts=posts[(~posts.title_clean.str.lower().isin(bad)) | (posts.selftext_clean.str.len()>0)]
    posts=posts[(posts.title_clean.str.len()>0) | (posts.selftext_clean.str.len()>0)]
    idcol=next((c for c in ["id","post_id","name"] if c in posts), None)
    if idcol: posts=posts.drop_duplicates(idcol)
    else: posts=posts.drop_duplicates(["subreddit_normalized","title_clean","selftext_clean"])
    rng=seed
    rows=[]; short=[]
    for name in names:
        group=posts[posts.subreddit_normalized==name]
        if len(group)<8: short.append((name,len(group))); continue
        sample=group.sample(n=8, random_state=rng).reset_index(drop=True)
        for rank,row in sample.iterrows(): rows.append({"subreddit":name,"sample_rank":rank+1,"post_id":str(row[idcol]) if idcol else "","title":row.title_clean,"selftext":row.selftext_clean})
    result=pd.DataFrame(rows, columns=["subreddit","sample_rank","post_id","title","selftext"])
    Path(output).parent.mkdir(parents=True,exist_ok=True); result.to_parquet(output,index=False)
    print(f"Prepared {result.subreddit.nunique() if len(result) else 0} subreddits / {len(result)} submissions")
    if short:
        print("Fewer than eight usable submissions:")
        for n,count in short: print(f"  {n}: {count}")
    return result, short
if __name__=="__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--subreddits",required=True); ap.add_argument("--submissions",required=True); ap.add_argument("--output",required=True); ap.add_argument("--seed",type=int,default=SEED); ap.add_argument("--limit",type=int,default=250, help="Number of subreddits to prepare; 0 means all")
    a=ap.parse_args(); prepare(a.subreddits,a.submissions,a.output,a.seed,a.limit)
