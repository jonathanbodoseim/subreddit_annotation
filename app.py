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
            primary=st.radio("Stage-2 label *", ["", "stock_investing_core", "other_stock_market"], format_func=lambda x:"Select…" if not x else x)
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
def adjudication_page(annotator):
    with db.connect(DB_PATH) as c:
        rows=c.execute("SELECT subreddit, GROUP_CONCAT(annotator_id||': '||primary_category, ' | ') labels FROM stage1_annotations GROUP BY subreddit HAVING COUNT(*) >= 2 ORDER BY subreddit").fetchall()
    st.subheader("Stage 1 adjudication")
    st.info("Only cases with two independent Stage 1 labels appear here. Adjudicated labels are stored separately from raw labels.")
    for row in rows:
        with st.expander(f"r/{row['subreddit']} — {row['labels']}"):
            with st.form(f"adj_{row['subreddit']}"):
                label=st.selectbox("Adjudicated label", [""]+list(TAXONOMY), key=f"adjlabel_{row['subreddit']}")
                rationale=st.text_area("Adjudication rationale", key=f"adjrat_{row['subreddit']}")
                if st.form_submit_button("Save adjudication"):
                    if not label: st.error("Choose a label.")
                    else:
                        db.save_adjudication(DB_PATH,row['subreddit'],label,rationale,annotator); st.success("Saved."); st.rerun()
def main():
    db.init_db(DB_PATH); definitions()
    st.title("Two-stage subreddit annotation")
    if not DATASET_PATH.exists(): st.error(f"Prepared dataset not found: {DATASET_PATH}"); st.stop()
    try: df=load_data(str(DATASET_PATH))
    except Exception as exc: st.error(f"Could not load prepared dataset: {exc}"); st.stop()
    annotator=st.sidebar.selectbox("Assigned annotator ID", ANNOTATOR_IDS)
    role=st.sidebar.radio("Workspace", ["Stage 1 annotation","Adjudication","Stage 2 annotation","Exports"])
    if role=="Stage 1 annotation": annotation_page(df,annotator,1)
    elif role=="Adjudication": adjudication_page(annotator)
    elif role=="Stage 2 annotation":
        stock=db.adjudicated_stock(DB_PATH); subset=df[df.subreddit.isin(stock)]
        if not stock: st.warning("Stage 2 is locked until adjudicated stock_market labels are available.")
        else: annotation_page(subset,annotator,2)
    else:
        st.subheader("Exports")
        st.write("Exports include raw independent annotations, adjudications, and Stage 2 labels.")
        if st.button("Generate CSV exports"): db.export_csv(DB_PATH,OUTPUT_DIR); st.success(f"Saved CSV files to {OUTPUT_DIR}")
if __name__=="__main__": main()
