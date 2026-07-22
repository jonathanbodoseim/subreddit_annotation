import logging, time, hashlib
from pathlib import Path
from urllib.parse import quote
import pandas as pd
import streamlit as st
from config import DATASET_PATH, DB_PATH, OUTPUT_DIR, ANNOTATOR_IDS, SEED
from taxonomy import TAXONOMY, STAGE2_TAXONOMY
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
        for number,details in enumerate(STAGE2_TAXONOMY.values(),1):
            st.markdown(f"**{number}. {details['title']}**")
            st.markdown(f"**Core purpose:** {details['core_purpose']}")
            st.markdown(f"**Typical content:** {details['typical_content']}")
def move_cursor(key,delta,total):
    st.session_state[key]=max(0,min(total-1,st.session_state.get(key,0)+delta))
def jump_cursor(cursor_key,jump_key,total):
    move_cursor(cursor_key,st.session_state.get(jump_key,0),total)
    st.session_state[jump_key]=0
def annotation_page(df, annotator, stage):
    version="four_categories" if stage==2 else "taxonomy_32"
    done_key=f"completed_{version}_{annotator}"
    if done_key not in st.session_state:
        st.session_state[done_key]=db.completed(DB_PATH,stage,annotator)
    eligible=ordered(df.subreddit.unique().tolist(),annotator,stage)
    if not eligible: st.success("No cases are assigned to this stage."); return
    done=st.session_state[done_key]
    completed_count=len(set(eligible)&done)
    st.progress(completed_count/len(eligible),text=f"Stage {stage}: {completed_count} / {len(eligible)} completed")
    cursor_key=f"cursor_{version}_{annotator}"
    if cursor_key not in st.session_state:
        st.session_state[cursor_key]=next((i for i,name in enumerate(eligible) if name not in done),len(eligible)-1)
    index=max(0,min(len(eligible)-1,st.session_state[cursor_key])); st.session_state[cursor_key]=index
    nav1,nav2=st.columns(2)
    nav1.button("← Previous case",disabled=index==0,use_container_width=True,on_click=move_cursor,args=(cursor_key,-1,len(eligible)))
    nav2.button("Next case →",disabled=index==len(eligible)-1,use_container_width=True,on_click=move_cursor,args=(cursor_key,1,len(eligible)))
    subreddit=eligible[index]; samples=df[df.subreddit==subreddit].sort_values("sample_rank")
    existing=db.get_annotation(DB_PATH,stage,annotator,subreddit) if subreddit in done else None
    reddit_url=f"https://www.reddit.com/r/{quote(subreddit,safe='')}/"
    st.markdown(f"## [r/{subreddit}]({reddit_url})")
    st.caption(f"Case {index+1} of {len(eligible)} · {'saved — you can update it' if existing else 'not yet saved'}")
    started=st.session_state.setdefault(f"started_{stage}_{subreddit}", time.monotonic())
    for _,row in samples.iterrows():
        with st.expander(f"{int(row.sample_rank)}. {row.title or '(no title)'}"):
            st.write(row.selftext or "(no self-text)")
    choices=sorted(TAXONOMY) if stage==1 else list(STAGE2_TAXONOMY)
    default_label=existing["label"] if existing else None
    default_label=default_label if default_label in choices else None
    default_confidence=existing["confidence"] if existing and existing["confidence"] in [1,2,3,4,5] else None
    with st.form(f"annotation_{version}_{subreddit}"):
        primary=st.pills("Choose a category *",choices,selection_mode="single",default=default_label,format_func=(lambda value: STAGE2_TAXONOMY[value]["title"]) if stage==2 else None)
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
    jump_key=f"jump_{version}_{annotator}"
    jump_col,button_col=st.columns([4,1])
    jump_col.slider("Jump backward or forward",-10,10,0,key=jump_key,help="Choose a negative number to move back or a positive number to move ahead.")
    button_col.button("Move",use_container_width=True,on_click=jump_cursor,args=(cursor_key,jump_key,len(eligible)))
def main():
    st.title("Two-stage subreddit annotation")
    log.info("Starting application session")
    try:
        log.info("Initializing database")
        initialize_database(str(DB_PATH))
        log.info("Database initialization complete")
    except Exception as exc:
        log.exception("Database initialization failed")
        st.error("The annotation database could not be reached. Please check the Streamlit app logs and Supabase project status.")
        st.stop()
    definitions()
    if not DATASET_PATH.exists(): st.error(f"Prepared dataset not found: {DATASET_PATH}"); st.stop()
    try:
        df=load_data(str(DATASET_PATH))
        log.info("Annotation dataset loaded")
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
