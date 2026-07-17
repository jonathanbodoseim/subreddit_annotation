from pathlib import Path
import os

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
DB_PATH = Path(os.getenv("ANNOTATION_DB_PATH", str(OUTPUT_DIR / "annotations.sqlite3")))
DATASET_PATH = Path(os.getenv("ANNOTATION_DATASET_PATH", str(DATA_DIR / "clean_samples.parquet")))
SEED = int(os.getenv("ANNOTATION_SEED", "20240717"))
ANNOTATOR_IDS = [x.strip() for x in os.getenv("ANNOTATOR_IDS", "annotator_1,annotator_2").split(",") if x.strip()]
