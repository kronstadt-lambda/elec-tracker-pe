import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / os.getenv("DATA_DIR", "data/raw")
ONPE_PRE_URL = os.getenv("ONPE_PRESIDENCIAL_URL")
ONPE_PC_URL = os.getenv("ONPE_PARTICIPACION_CIUDADANA")

DATA_DIR.mkdir(parents=True, exist_ok=True)