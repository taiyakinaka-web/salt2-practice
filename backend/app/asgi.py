"""Runtime entrypoint; importing the application factory does not initialize storage."""
from dotenv import load_dotenv

from .main import ROOT, create_app

load_dotenv(ROOT / ".env")
app = create_app()
