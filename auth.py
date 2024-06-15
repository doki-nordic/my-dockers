
import secrets
from pathlib import Path

file = Path(__file__).parent / 'data/private-key.txt'
if file.exists():
    auth_key = file.read_text().strip()
else:
    auth_key = secrets.token_urlsafe(20)
    file.write_text(auth_key)
