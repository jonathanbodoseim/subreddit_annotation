import logging, time, hashlib
from pathlib import Path
import pandas as pd
import streamlit as st
from config import DATASET_PATH, DB_PATH, OUTPUT_DIR, ANNOTATOR_IDS, SEED
from taxonomy import TAXONOMY
import database as db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log=logging.getLogger(__name__)
st.set_page_config(page_title="Subreddit annotation", layout="wide")

@st.cache_data
def load_data(path):
    df=pd.read_parquet(path)
    required={"subreddit","sample_rank","title","selftext"}
    if not required.issubset(df.columns): raise ValueError(f"Dataset must contain {sorted(required)}")
    return df
def ordered(names, annotator, stage):
    return sorted(names, key=lambda x: hashlib.sha256(f"{SEED}:{stage}:{annotator}:{x}".encode()).hexdigest())
def flags(key):
    return st.multiselect("Ambiguity flags (optional)", ["unclear topic", "mixed topics", "insufficient evidence", "taxonomy boundary", "low-quality sample"], key=key)
def definitions():
    with st.sidebar.expander("Taxonomy definitions (always available)", expanded=False):
        for k,v in TAXONOMY.items(): st.markdown(f"**{k}** — {v}")
def annotation_page(df, annotator, stage):
    done=db.completed(DB_PATH,stage,annotator)
    eligible=ordered(df.subreddit.unique().tolist(),annotator,stage)
    remaining=[x for x in eligible if x not in done]
    st.progress(len(done)/len(eligible) if eligible else 1.0, text=f"Stage {stage}: {len(done)} / {len(eligible)} completed")
    if not remaining: st.success("All assigned cases are complete."); return
    subreddit=remaining[0]; samples=df[df.subreddit==subreddit].sort_values("sample_rank")
    st.subheader(f"r/{subreddit}")
    st.caption(f"Case {len(done)+1} of {len(eligible)} · timer starts when this case is shown")
    started=st.session_state.setdefault(f"started_{stage}_{subreddit}", time.monotonic())
    for _,row in samples.iterrows():
        with st.expander(f"{int(row.sample_rank)}. {row.title or '(no title)'}"):
            st.write(row.selftext or "(no self-text)")
    with st.form(f"form_{stage}_{subreddit}"):
        if stage==1:
            primary=st.selectbox("Primary category *", [""]+list(TAXONOMY), format_func=lambda x: "Select…" if not x else x)
            second=st.selectbox("Second-choice category *", [""]+list(TAXONOMY), format_func=lambda x: "Select…" if not x else x)
        else:
            primary=st.radio("Stage-2 label *", ["", "serious_investing", "residual"], format_func=lambda x:"Select…" if not x else x)
            second=""
        confidence=st.radio("Confidence (1 = low, 5 = high) *", [1,2,3,4,5], horizontal=True, index=None)
        ambiguity=flags(f"flags_{stage}_{subreddit}")
        rationale=st.text_area("Short rationale (optional)", max_chars=1000)
        submitted=st.form_submit_button("Save and continue")
    if submitted:
        errors=[]
        if not primary: errors.append("Choose a label.")
        if stage==1 and (not second or second==primary): errors.append("Choose a distinct second-choice category.")
        if confidence is None: errors.append("Choose a confidence score.")
        if errors:
            for e in errors: st.error(e)
        else:
            seconds=max(0,int(time.monotonic()-started)); created=db.now()
            try:
                if stage==1: db.save_stage1(DB_PATH,(subreddit,annotator,primary,second,confidence,";".join(ambiguity),rationale,seconds,created))
                else: db.save_stage2(DB_PATH,(subreddit,annotator,primary,confidence,";".join(ambiguity),rationale,seconds,created))
                st.session_state.pop(f"started_{stage}_{subreddit}",None); st.rerun()
            except Exception as exc:
                log.exception("Could not save annotation"); st.error(f"Could not save this case: {exc}")
def main():
    db.init_db(DB_PATH); definitions()
    st.title("Two-stage subreddit annotation")
    if not DATASET_PATH.exists(): st.error(f"Prepared dataset not found: {DATASET_PATH}"); st.stop()
    try: df=load_data(str(DATASET_PATH))
    except Exception as exc: st.error(f"Could not load prepared dataset: {exc}"); st.stop()
    annotator=st.sidebar.selectbox("Assigned annotator ID", ANNOTATOR_IDS)
    role=st.sidebar.radio("Workspace", ["Stage 1 annotation","Stage 2 annotation","Exports"])
    if role=="Stage 1 annotation": annotation_page(df,annotator,1)
    elif role=="Stage 2 annotation":
        stock=db.stage1_stock(DB_PATH, annotator); subset=df[df.subreddit.isin(stock)]
        if not stock: st.warning("Stage 2 is locked until you have saved at least one Stage 1 stock_market label.")
        else: annotation_page(subset,annotator,2)
    else:
        st.subheader("Exports")
        st.write("Each annotator exports two files: one Stage 1 file and one Stage 2 file. Raw labels are never overwritten.")
        if st.button("Generate my two CSV exports"): db.export_annotator_csv(DB_PATH,OUTPUT_DIR,annotator); st.success(f"Saved {annotator}_stage1.csv and {annotator}_stage2.csv to {OUTPUT_DIR}")
if __name__=="__main__": main()
