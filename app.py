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
def stage2_definitions():
    with st.sidebar.expander("Stage 2 definitions",expanded=True):
        st.markdown("""
**General communities:** Broad communities that serve as general entry points for learning about stock investing, analysing securities, and managing portfolios.

**Specialized communities:** Communities centred on active trading, particular securities or instruments, speculative episodes, memes, or entertainment.
""")
def move_cursor(key,delta,total):
    st.session_state[key]=max(0,min(total-1,st.session_state.get(key,0)+delta))
def jump_cursor(cursor_key,jump_key,total):
    move_cursor(cursor_key,st.session_state.get(jump_key,0),total)
    st.session_state[jump_key]=0
def annotation_page(df, annotator, stage):
    done_key=f"completed_{stage}_{annotator}"
    if done_key not in st.session_state:
        st.session_state[done_key]=db.completed(DB_PATH,stage,annotator)
    eligible=ordered(df.subreddit.unique().tolist(),annotator,stage)
    if not eligible: st.success("No cases are assigned to this stage."); return
    done=st.session_state[done_key]
    completed_count=len(set(eligible)&done)
    st.progress(completed_count/len(eligible),text=f"Stage {stage}: {completed_count} / {len(eligible)} completed")
    cursor_key=f"cursor_{stage}_{annotator}"
    if cursor_key not in st.session_state:
        st.session_state[cursor_key]=next((i for i,name in enumerate(eligible) if name not in done),len(eligible)-1)
    index=max(0,min(len(eligible)-1,st.session_state[cursor_key])); st.session_state[cursor_key]=index
    nav1,nav2=st.columns(2)
    nav1.button("← Previous case",disabled=index==0,use_container_width=True,on_click=move_cursor,args=(cursor_key,-1,len(eligible)))
    nav2.button("Next case →",disabled=index==len(eligible)-1,use_container_width=True,on_click=move_cursor,args=(cursor_key,1,len(eligible)))
    subreddit=eligible[index]; samples=df[df.subreddit==subreddit].sort_values("sample_rank")
    existing=db.get_annotation(DB_PATH,stage,annotator,subreddit) if subreddit in done else None
    st.subheader(f"r/{subreddit}")
    st.caption(f"Case {index+1} of {len(eligible)} · {'saved — you can update it' if existing else 'not yet saved'}")
    started=st.session_state.setdefault(f"started_{stage}_{subreddit}", time.monotonic())
    for _,row in samples.iterrows():
        with st.expander(f"{int(row.sample_rank)}. {row.title or '(no title)'}"):
            st.write(row.selftext or "(no self-text)")
    choices=sorted(TAXONOMY) if stage==1 else ["general_communities", "specialized_communities"]
    legacy_stage2={"serious_investing":"general_communities","residual":"specialized_communities"}
    default_label=legacy_stage2.get(existing["label"],existing["label"]) if existing and stage==2 else (existing["label"] if existing else None)
    default_label=default_label if default_label in choices else None
    default_confidence=existing["confidence"] if existing and existing["confidence"] in [1,2,3,4,5] else None
    with st.form(f"annotation_{stage}_{subreddit}"):
        primary=st.pills("Choose a category *",choices,selection_mode="single",default=default_label)
        confidence=st.radio("Confidence (1 = low, 5 = high) *",[1,2,3,4,5],horizontal=True,index=default_confidence-1 if default_confidence else None)
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
                next_index=next((i for i in range(index+1,len(eligible)) if eligible[i] not in done),min(index+1,len(eligible)-1))
                st.session_state[cursor_key]=next_index
                st.session_state.pop(f"started_{stage}_{subreddit}",None); st.rerun()
            except Exception as exc:
                log.exception("Could not save annotation"); st.error(f"Could not save this case: {exc}")
    st.divider()
    jump_key=f"jump_{stage}_{annotator}"
    jump_col,button_col=st.columns([4,1])
    jump_col.slider("Jump backward or forward",-10,10,0,key=jump_key,help="Choose a negative number to move back or a positive number to move ahead.")
    button_col.button("Move",use_container_width=True,on_click=jump_cursor,args=(cursor_key,jump_key,len(eligible)))
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
        stage2_definitions()
        annotation_page(df[df.stage2_eligible],annotator,2)
    else:
        st.subheader("Exports")
        st.write("Each annotator exports two files: one Stage 1 file and one Stage 2 file. Raw labels are never overwritten.")
        if st.button("Generate my two CSV exports"): db.export_annotator_csv(DB_PATH,OUTPUT_DIR,annotator); st.success(f"Saved {annotator}_stage1.csv and {annotator}_stage2.csv to {OUTPUT_DIR}")
if __name__=="__main__": main()
