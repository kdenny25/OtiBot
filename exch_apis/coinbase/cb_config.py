from dotenv import load_dotenv
from pathlib import Path
import os

env_path = Path('...') / '.env'
load_dotenv(dotenv_path=env_path)

class cb_settings:
    USER_ID:str = 'COINBASE_USER_ID'
    PROFILE_ID:str = 'COINBASE_PROFILE_ID'


