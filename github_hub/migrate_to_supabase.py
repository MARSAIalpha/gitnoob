"""
Data Migration Script: SQLite -> Supabase
Run this ONCE to migrate existing data.
"""
import sqlite3
import json
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from supabase import create_client
from config import SUPABASE_URL, SUPABASE_KEY, DATABASE_PATH

def migrate():
    # Connect to local SQLite
    base_dir = os.path.dirname(os.path.abspath(__file__))
    sqlite_path = os.path.join(base_dir, DATABASE_PATH)
    
    if not os.path.exists(sqlite_path):
        print(f"SQLite DB not found at {sqlite_path}")
        return
    
    print(f"Connecting to SQLite: {sqlite_path}")
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Connect to Supabase
    print(f"Connecting to Supabase: {SUPABASE_URL}")
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    # Migrate Projects
    print("\n--- Migrating Projects ---")
    cursor.execute("SELECT * FROM projects")
    projects = cursor.fetchall()
    print(f"Found {len(projects)} projects")
    
    for row in projects:
        data = dict(row)
        # Parse JSON fields
        for field in ['topics', 'ai_tech_stack', 'ai_use_cases']:
            if data.get(field):
                try:
                    data[field] = json.loads(data[field])
                except:
                    data[field] = []
            else:
                data[field] = []
        
        # Convert id to string
        data['id'] = str(data['id'])
        
        try:
            supabase.table("projects").upsert(data).execute()
            print(f"  Migrated: {data['name']}")
        except Exception as e:
            print(f"  Error migrating {data['name']}: {e}")
    
    # Migrate News Sources
    print("\n--- Migrating News Sources ---")
    try:
        cursor.execute("SELECT * FROM news_sources")
        sources = cursor.fetchall()
        print(f"Found {len(sources)} news sources")
        
        for row in sources:
            data = dict(row)
            # Remove auto-increment id (Supabase will generate new one)
            del data['id']
            try:
                supabase.table("news_sources").upsert(data, on_conflict="url").execute()
                print(f"  Migrated: {data['name']}")
            except Exception as e:
                print(f"  Error migrating {data['name']}: {e}")
    except Exception as e:
        print(f"  No news_sources table or error: {e}")
    
    # Migrate Settings
    print("\n--- Migrating Settings ---")
    try:
        cursor.execute("SELECT * FROM settings")
        settings = cursor.fetchall()
        print(f"Found {len(settings)} settings")
        
        for row in settings:
            data = dict(row)
            try:
                supabase.table("settings").upsert(data).execute()
                print(f"  Migrated: {data['key']}")
            except Exception as e:
                print(f"  Error migrating {data['key']}: {e}")
    except Exception as e:
        print(f"  No settings table or error: {e}")
    
    conn.close()
    print("\n✅ Migration complete!")

if __name__ == "__main__":
    migrate()
