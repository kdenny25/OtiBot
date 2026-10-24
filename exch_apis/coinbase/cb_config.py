from dotenv import load_dotenv
from pathlib import Path
import os

env_path = Path(__file__).resolve().parents[2] / '.env'
load_dotenv(dotenv_path=env_path)

class cb_settings:
    USER_ID:str = os.getenv('COINBASE_USER_ID')
    PROFILE_ID:str = os.getenv('COINBASE_PROFILE_ID')
