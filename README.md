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

Both annotators independently complete the same fixed random Stage 1 sample of 250 eligible subreddits. Stage 2 contains every eligible subreddit whose LLM `primary` label in the taxonomy CSV is `stock_market`; it does not depend on either annotator's Stage 1 choices. Stage 2 uses `serious_investing` versus `residual`, with the same eight sampled submissions. Use Exports to write exactly two CSV files per annotator: `<annotator>_stage1.csv` and `<annotator>_stage2.csv`.

The preparation script normalizes `subreddit`/`source_subreddit`, removes empty/deleted/removed posts and duplicates, samples exactly eight per eligible subreddit with a fixed seed, and prints the shortfall list.
It defaults to a deterministic 250-subreddit task (`--limit 0` prepares all names); the limit is applied before the Parquet scan.

## Tests and deployment

```powershell
pytest -q
```

For deployment, use a shared PostgreSQL/Supabase implementation and persistent secrets/environment variables; do not use ephemeral local SQLite storage. Streamlit Community Cloud requires an external database for simultaneous annotators.

The supplied files use `subreddit` in the CSV and `subreddit`, `title`, `selftext`, and `id` in the Parquet. The script also accepts common aliases and reports the detected schema error when none match.

## Cloud database

Local runs use SQLite. For Streamlit Community Cloud, create a Supabase PostgreSQL project and add its connection string in the app Secrets as:

```toml
DATABASE_URL = "postgresql://..."
```

The app automatically selects PostgreSQL when `DATABASE_URL` is present and initializes its tables on first start. Never commit the connection string. Keep regular CSV exports and database backups.
