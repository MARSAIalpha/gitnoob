"""Debug: Check what categories exist in Supabase"""
import sys
sys.path.insert(0, '.')

from supabase import create_client
from config import SUPABASE_URL, SUPABASE_KEY

client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Get distinct categories
response = client.table("projects").select("category").execute()

# Count by category
category_counts = {}
for row in response.data:
    cat = row.get('category', 'unknown')
    category_counts[cat] = category_counts.get(cat, 0) + 1

print("Categories found in database:")
for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
    print(f"  {cat}: {count}")
