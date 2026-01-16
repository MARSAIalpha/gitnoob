# GitHub Hub - Database Layer (Supabase PostgreSQL)
import json
import threading
from datetime import datetime
from typing import Optional, List, Dict
from supabase import create_client, Client
from config import SUPABASE_URL, SUPABASE_KEY

class Database:
    """Database layer using Supabase PostgreSQL"""
    
    def __init__(self, db_path: str = None):
        """Initialize Supabase client. db_path is ignored (legacy compat)."""
        self.lock = threading.RLock()  # Keep for thread safety
        try:
            self.supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
            print(f"Connected to Supabase: {SUPABASE_URL}")
        except Exception as e:
            print(f"Error connecting to Supabase: {e}")
            self.supabase = None
    
    def _ensure_client(self):
        """Check if Supabase client is available"""
        if not self.supabase:
            raise Exception("Supabase client not initialized")
    
    # ========== Projects ==========
    
    def upsert_project(self, project: dict):
        """Insert or update a project"""
        self._ensure_client()
        now = datetime.now().isoformat()
        
        # Prepare data for PostgreSQL
        data = {
            "id": str(project['id']),
            "name": project['name'],
            "full_name": project['full_name'],
            "category": project['category'],
            "stars": project.get('stars', 0),
            "forks": project.get('forks', 0),
            "description": project.get('description'),
            "url": project.get('url'),
            "homepage": project.get('homepage'),
            "language": project.get('language'),
            "topics": project.get('topics', []),  # JSONB in PostgreSQL
            "created_at": project.get('created_at'),
            "updated_at": project.get('updated_at'),
            "last_scanned": now,
        }
        
        with self.lock:
            self.supabase.table("projects").upsert(data).execute()
    
    def get_all_projects(self) -> List[Dict]:
        """Get all projects"""
        self._ensure_client()
        response = self.supabase.table("projects").select("*").execute()
        return [dict(row) for row in response.data]
    
    def get_projects_by_category(self, category: str, limit: int = 100) -> List[Dict]:
        """Get projects by category"""
        self._ensure_client()
        response = self.supabase.table("projects").select("*").eq("category", category).limit(limit).execute()
        return [dict(row) for row in response.data]
    
    def get_project(self, project_id: str) -> Optional[Dict]:
        """Get single project by ID"""
        self._ensure_client()
        response = self.supabase.table("projects").select("*").eq("id", str(project_id)).execute()
        if response.data:
            return dict(response.data[0])
        return None
    
    def delete_project(self, project_id: str):
        """Delete a project"""
        self._ensure_client()
        with self.lock:
            self.supabase.table("projects").delete().eq("id", str(project_id)).execute()
    
    def update_project_analysis(self, project_id: str, analysis: dict):
        """Update AI analysis fields"""
        self._ensure_client()
        now = datetime.now().isoformat()
        
        update_data = {
            "ai_summary": analysis.get('summary'),
            "ai_tech_stack": analysis.get('tech_stack', []),
            "ai_use_cases": analysis.get('use_cases', []),
            "ai_difficulty": analysis.get('difficulty'),
            "ai_quick_start": analysis.get('quick_start'),
            "ai_model_name": analysis.get('model_name'),  # Store which model did the analysis
            "last_analyzed": now
        }
        
        with self.lock:
            self.supabase.table("projects").update(update_data).eq("id", str(project_id)).execute()
            
    def update_ai_analysis(self, project_id: str, analysis: dict):
        """Alias for backward compatibility"""
        self.update_project_analysis(project_id, analysis)
    
    def update_project_tutorial(self, project_id: str, tutorial: str):
        """Update tutorial content"""
        self._ensure_client()
        with self.lock:
            self.supabase.table("projects").update({"ai_tutorial": tutorial}).eq("id", str(project_id)).execute()
    
    def update_project_rag_summary(self, project_id: str, summary: str):
        """Update RAG summary"""
        self._ensure_client()
        with self.lock:
            self.supabase.table("projects").update({"ai_rag_summary": summary}).eq("id", str(project_id)).execute()
    
    def update_project_screenshot(self, project_id: str, screenshot_path: str):
        """Update screenshot path"""
        self._ensure_client()
        with self.lock:
            self.supabase.table("projects").update({"screenshot": screenshot_path}).eq("id", str(project_id)).execute()
    
    def update_project_visual_summary(self, project_id: str, summary: str):
        """Update visual summary"""
        self._ensure_client()
        with self.lock:
            self.supabase.table("projects").update({"ai_visual_summary": summary}).eq("id", str(project_id)).execute()
    
    def get_projects_needing_analysis(self, limit: int = 10, target_model: str = "120b") -> List[Dict]:
        """
        Get projects that need analysis.
        Prioritizes projects that have NO analysis or analysis from a different model.
        """
        self._ensure_client()
        
        # 1. First, try to get completely unanalyzed projects
        response = self.supabase.table("projects").select("*").is_("ai_summary", "null").limit(limit).execute()
        pending = [dict(row) for row in response.data]
        
        # 2. If we still have room, get projects that haven't been analyzed by the target_model
        if len(pending) < limit:
            remaining = limit - len(pending)
            # Use 'not ilike' if possible, or just fetch and filter locally for simplicity since limit is small
            # Supabase doesn't have a direct 'not ilike' in the basic client wrapper sometimes, 
            # let's just fetch projects that have a summary but NO model name, or model name != target_model
            response = self.supabase.table("projects").select("*")\
                .not_.is_("ai_summary", "null")\
                .not_.ilike("ai_model_name", f"%{target_model}%")\
                .limit(remaining).execute()
            pending.extend([dict(row) for row in response.data])
            
        return pending
        
    def get_unanalyzed_projects(self, limit: int = 10) -> List[Dict]:
        """Alias for backward compatibility"""
        return self.get_projects_needing_analysis(limit=limit)
    
    def search_projects(self, query: str) -> List[Dict]:
        """Full-text search on projects"""
        self._ensure_client()
        # Use PostgreSQL ilike for basic search
        response = self.supabase.table("projects").select("*").or_(
            f"name.ilike.%{query}%,description.ilike.%{query}%,ai_rag_summary.ilike.%{query}%"
        ).execute()
        return [dict(row) for row in response.data]
    
    def get_pending_count(self) -> int:
        """Get count of projects pending analysis (lacking 120B analysis)"""
        self._ensure_client()
        # Strictly count those without 120b analysis
        try:
            total_res = self.supabase.table("projects").select("id", count="exact").execute()
            total = total_res.count or 0
            
            analyzed_res = self.supabase.table("projects").select("id", count="exact").ilike("ai_model_name", "%120b%").execute()
            analyzed = analyzed_res.count or 0
            
            return max(0, total - analyzed)
        except Exception as e:
            print(f"Error getting pending count: {e}")
            return 0
    
    def get_tutorial(self, project_id: str) -> Optional[str]:
        """Get tutorial for a project"""
        project = self.get_project(project_id)
        if project:
            return project.get('ai_tutorial')
        return None
    
    def get_stats(self) -> Dict:
        """Get database statistics"""
        self._ensure_client()
        
        # Total projects
        total = 0
        try:
            total_response = self.supabase.table("projects").select("id", count="exact").execute()
            total = total_response.count if total_response.count is not None else 0
        except Exception as e:
            print(f"Error getting total count: {e}")
            
        # Analyzed projects
        analyzed = 0
        try:
            # Try to count only those analyzed by 120B model
            analyzed_response = self.supabase.table("projects").select("id", count="exact")\
                .ilike("ai_model_name", "%120b%").execute()
            analyzed = analyzed_response.count if analyzed_response.count is not None else 0
        except Exception as e:
            # Fallback: Count any project with an ai_summary
            print(f"Error getting 120B count (probably column missing): {e}")
            try:
                analyzed_response = self.supabase.table("projects").select("id", count="exact").not_.is_("ai_summary", "null").execute()
                analyzed = analyzed_response.count if analyzed_response.count is not None else 0
            except Exception as e2:
                print(f"Error getting basic analyzed count: {e2}")
        
        # Categories
        cat_count = 0
        try:
            categories_response = self.supabase.table("projects").select("category").execute()
            categories = list(set(row['category'] for row in categories_response.data))
            cat_count = len(categories)
        except Exception as e:
            print(f"Error getting categories: {e}")
            
        return {
            "total_projects": total,
            "analyzed_projects": analyzed,
            "categories": cat_count
        }
    
    # ========== Scan History ==========
    
    def log_scan(self, category: str, found: int, new: int, status: str):
        """Log a scan event"""
        self._ensure_client()
        data = {
            "category": category,
            "projects_found": found,
            "projects_new": new,
            "status": status
        }
        with self.lock:
            self.supabase.table("scan_history").insert(data).execute()
    
    def get_recent_scans(self, limit: int = 20) -> List[Dict]:
        """Get recent scan history"""
        self._ensure_client()
        response = self.supabase.table("scan_history").select("*").order("scan_time", desc=True).limit(limit).execute()
        return [dict(row) for row in response.data]
    
    # ========== Settings ==========
    
    def get_setting(self, key: str, default: str = None) -> Optional[str]:
        """Get a setting value"""
        self._ensure_client()
        response = self.supabase.table("settings").select("value").eq("key", key).execute()
        if response.data:
            return response.data[0]['value']
        return default
    
    def set_setting(self, key: str, value: str):
        """Set a setting value"""
        self._ensure_client()
        with self.lock:
            self.supabase.table("settings").upsert({"key": key, "value": value}).execute()
    
    # ========== News Sources ==========
    
    def get_news_sources(self) -> List[Dict]:
        """Get all news sources"""
        self._ensure_client()
        response = self.supabase.table("news_sources").select("*").execute()
        return [dict(row) for row in response.data]
    
    def add_news_source(self, name: str, url: str):
        """Add a news source"""
        self._ensure_client()
        data = {
            "name": name,
            "url": url
        }
        with self.lock:
            try:
                self.supabase.table("news_sources").insert(data).execute()
            except Exception as e:
                print(f"Error adding news source (may already exist): {e}")
    
    def delete_news_source(self, source_id: int):
        """Delete a news source"""
        self._ensure_client()
        with self.lock:
            self.supabase.table("news_sources").delete().eq("id", source_id).execute()
    
    def update_news_source_scan_time(self, source_id: int):
        """Update last scan time for a news source"""
        self._ensure_client()
        with self.lock:
            self.supabase.table("news_sources").update({"last_scanned": datetime.now().isoformat()}).eq("id", source_id).execute()
    
    def get_all_categories_summary(self) -> Dict:
        """Get summary of projects by category"""
        self._ensure_client()
        try:
            response = self.supabase.table("projects").select("category").execute()
            
            # Count projects per category
            category_counts = {}
            for row in response.data:
                cat = row.get('category', 'other')
                category_counts[cat] = category_counts.get(cat, 0) + 1
            
            return category_counts
        except Exception as e:
            print(f"Error getting categories summary: {e}")
            return {}
