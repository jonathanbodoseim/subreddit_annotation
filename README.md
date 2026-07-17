# Two-stage subreddit annotation

Streamlit app for independent two-annotator taxonomy labeling, separate adjudication, and a stock-market binary follow-up.

## Setup

```powershell
cd subreddit_annotation
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Copy no source data into Git. Prepare a local dataset:

```powershell
python prepare_data.py --subreddits C:\path\subreddits.csv --submissions C:\path\submissions.parquet --output data\clean_samples.parquet
streamlit run app.py
```

SQLite is initialized automatically at `output/annotations.sqlite3`; set `ANNOTATION_DB_PATH` and `ANNOTATION_DATASET_PATH` to relocate them. WAL mode and uniqueness constraints protect progress and duplicate submissions for two concurrent annotators. PostgreSQL/Supabase can replace `database.py` behind its small function interface.

## Workflow

Both annotators independently complete Stage 1. An adjudicator selects a final label under Adjudication. Stage 2 then unlocks only adjudicated `stock_market` cases. Raw labels are never overwritten. Use Exports to write CSV files locally.

The preparation script normalizes `subreddit`/`source_subreddit`, removes empty/deleted/removed posts and duplicates, samples exactly eight per eligible subreddit with a fixed seed, and prints the shortfall list.
It defaults to a deterministic 250-subreddit task (`--limit 0` prepares all names); the limit is applied before the Parquet scan.

## Tests and deployment

```powershell
pytest -q
```

For deployment, use a shared PostgreSQL/Supabase implementation and persistent secrets/environment variables; do not use ephemeral local SQLite storage. Streamlit Community Cloud requires an external database for simultaneous annotators.

The supplied files use `subreddit` in the CSV and `subreddit`, `title`, `selftext`, and `id` in the Parquet. The script also accepts common aliases and reports the detected schema error when none match.
