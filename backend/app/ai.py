# Install: pip install backboard-sdk
import asyncio
from backboard import BackboardClient
from dotenv import load_dotenv

from pathlib import Path
load_dotenv(Path(__file__).parent.parent / ".env")
backboard_api_key = os.getenv("BACKBOARD")
backboard_client = BackboardClient(api_key=backboard_api_key)