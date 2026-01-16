"""Debug get_stats"""
import sys
sys.path.insert(0, '.')
from database import Database
import json

try:
    db = Database()
    stats = db.get_stats()
    print(f"Stats: {json.dumps(stats, indent=2)}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
