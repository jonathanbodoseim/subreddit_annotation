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
    required={"subreddit","sample_rank","title","selftext","stage1_eligible","stage2_eligible"}
    if not required.issubset(df.columns): raise ValueError(f"Dataset must contain {sorted(required)}")
    return df
@st.cache_resource
def initialize_database(path):
    db.init_db(path)
    return True
def ordered(names, annotator, stage):
    return sorted(names, key=lambda x: hashlib.sha256(f"{SEED}:{stage}:{annotator}:{x}".encode()).hexdigest())
def definitions():
    with st.sidebar.expander("Taxonomy definitions (always available)", expanded=False):
        for k in sorted(TAXONOMY): st.markdown(f"**{k}** — {TAXONOMY[k]}")
def annotation_page(df, annotator, stage):
    done_key=f"completed_{stage}_{annotator}"
    if done_key not in st.session_state:
        st.session_state[done_key]=db.completed(DB_PATH,stage,annotator)
    done=st.session_state[done_key]
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
    choices=sorted(TAXONOMY) if stage==1 else ["general_communities", "specialized_communities"]
    with st.form(f"annotation_{stage}_{subreddit}"):
        primary=st.pills("Choose a category *",choices,selection_mode="single")
        confidence=st.radio("Confidence (1 = low, 5 = high) *",[1,2,3,4,5],horizontal=True,index=None)
        submitted=st.form_submit_button("Save and continue",type="primary")
    if submitted:
        errors=[]
        if not primary: errors.append("Choose a category.")
        if confidence is None: errors.append("Choose a confidence score.")
        if errors:
            for e in errors: st.error(e)
        else:
            seconds=max(0,int(time.monotonic()-started)); created=db.now()
            try:
                if stage==1: db.save_stage1(DB_PATH,(subreddit,annotator,primary,"",confidence,"","",seconds,created))
                else: db.save_stage2(DB_PATH,(subreddit,annotator,primary,confidence,"","",seconds,created))
                done.add(subreddit)
                st.session_state.pop(f"started_{stage}_{subreddit}",None); st.rerun()
            except Exception as exc:
                log.exception("Could not save annotation"); st.error(f"Could not save this case: {exc}")
def main():
    initialize_database(str(DB_PATH)); definitions()
    st.title("Two-stage subreddit annotation")
    if not DATASET_PATH.exists(): st.error(f"Prepared dataset not found: {DATASET_PATH}"); st.stop()
    try: df=load_data(str(DATASET_PATH))
    except Exception as exc: st.error(f"Could not load prepared dataset: {exc}"); st.stop()
    annotator=st.sidebar.selectbox("Assigned annotator ID", ANNOTATOR_IDS)
    role=st.sidebar.radio("Workspace", ["Stage 1 annotation","Stage 2 annotation","Exports"])
    if role=="Stage 1 annotation": annotation_page(df[df.stage1_eligible],annotator,1)
    elif role=="Stage 2 annotation":
        st.markdown("""
**General communities:** Broad communities that serve as general entry points for learning about stock investing, analysing securities, and managing portfolios.

**Specialized communities:** Communities centred on active trading, particular securities or instruments, speculative episodes, memes, or entertainment.
""")
        annotation_page(df[df.stage2_eligible],annotator,2)
    else:
        st.subheader("Exports")
        st.write("Each annotator exports two files: one Stage 1 file and one Stage 2 file. Raw labels are never overwritten.")
        if st.button("Generate my two CSV exports"): db.export_annotator_csv(DB_PATH,OUTPUT_DIR,annotator); st.success(f"Saved {annotator}_stage1.csv and {annotator}_stage2.csv to {OUTPUT_DIR}")
if __name__=="__main__": main()
