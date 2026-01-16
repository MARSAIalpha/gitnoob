# GitHub Hub - Master Agent (任务调度)
import threading
import time
from datetime import datetime
from typing import Dict, Callable
from database import Database
from crawler import CrawlerAgent
from analyzer import AnalyzerAgent, ContentAgent
from config import CATEGORIES, DISCOVERY_URLS

class MasterAgent:
    """主控 Agent - 调度所有子任务"""
    
    def __init__(self, db_path: str = None):
        # db_path is now ignored - Database class uses Supabase
        self.db = Database(db_path)
        self.crawler = CrawlerAgent()
        self.analyzer = AnalyzerAgent()
        self.content = ContentAgent()
        self.is_running = False
        self.current_task = None
        self.progress = {"total": 0, "done": 0, "current": ""}
        self.callbacks = []
        self.auto_analysis_timer = None
        
        # Start auto-analysis scheduler
        self.start_auto_analysis_scheduler()

        # Ensure default news sources exist
        self._ensure_news_sources()
        
    def _ensure_news_sources(self):
        """如果新闻源为空，则加载默认新闻源"""
        try:
            sources = self.db.get_news_sources()
            if not sources:
                print("Initializing default news sources...")
                for url in DISCOVERY_URLS:
                    name = "GitHub Trending" if "trending" in url else "News Source"
                    if "since=weekly" in url:
                        name += " (Weekly)"
                    self.db.add_news_source(name, url)
        except Exception as e:
            print(f"Error initializing sources: {e}")
    
    def start_auto_analysis_scheduler(self):
        """启动后台自动分析调度器，每 10 分钟检查一次"""
        def check_and_analyze():
            while True:
                time.sleep(600)  # Wait 10 minutes
                if not self.is_running:
                    pending_count = self.db.get_pending_count()
                    if pending_count > 0:
                        self._notify(f"🤖 Auto-analysis starting: {pending_count} projects pending...", "info")
                        threading.Thread(target=self.run_batch_analysis, daemon=True).start()
        
        self.auto_analysis_timer = threading.Thread(target=check_and_analyze, daemon=True)
        self.auto_analysis_timer.start()
    
    def add_callback(self, callback: Callable):
        """添加进度回调"""
        self.callbacks.append(callback)
    
    def _notify(self, message: str, level: str = "info"):
        """通知所有回调"""
        for cb in self.callbacks:
            try:
                cb({"message": message, "level": level, "time": datetime.now().isoformat()})
            except:
                pass

    def stop_task(self):
        """停止当前任务"""
        if self.is_running:
            self.is_running = False
            self._notify("🛑 Update: Stopping current task... (Waiting for current step to finish)", "warning")
            return {"status": "stopping"}
        return {"status": "not_running"}
    
    def run_full_scan(self) -> Dict:
        """执行完整扫描流程"""
        if self.is_running:
            return {"error": "Scan already running"}
        
        self.is_running = True
        self.current_task = "full_scan"
        results = {"crawl": {}, "analyze": 0, "content": 0}
        
        try:
            # Step 0: 每日新闻发现 (News Discovery)
            self.run_news_scan()

            # Step 1: 爬取所有分类 (优先爬取项目少的分类)
            self._notify("Starting full scan (Priority: Low Count First)...", "info")
            self.progress = {"total": len(CATEGORIES), "done": 0, "current": "Crawling"}
            
            # 获取当前各分类数量
            cat_counts = self.db.get_all_categories_summary()
            
            # 排序：数量少的排前面
            sorted_cats = []
            for cat_id, cat_config in CATEGORIES.items():
                count = cat_counts.get(cat_id, {}).get('count', 0)
                sorted_cats.append((cat_id, cat_config, count))
            
            sorted_cats.sort(key=lambda x: x[2])
            
            for cat_id, cat_config, count in sorted_cats:
                self.progress["current"] = f"Crawling: {cat_config['name']} (Current: {count})"
                self._notify(f"Scanning {cat_config['name']} (Current: {count})...", "info")
                
                if cat_id == "trending":
                    projects = self.crawler.get_trending()
                elif cat_id == "new_releases":
                    projects = self.crawler.get_new_releases()
                else:
                    projects = self.crawler.search_by_keywords(cat_config["keywords"], cat_id)
                
                for project in projects:
                    self.db.upsert_project(project)
                
                results["crawl"][cat_id] = len(projects)
                self.progress["done"] += 1
                self._notify(f"Found {len(projects)} in {cat_config['name']}", "success")
            
            # Step 2: AI 分析未处理的项目
            self._notify("Starting AI analysis...", "info")
            pending = self.db.get_projects_needing_analysis(limit=50)
            self.progress = {"total": len(pending), "done": 0, "current": "Analyzing"}
            
            for project in pending:
                self.progress["current"] = f"Analyzing: {project['name']}"
                
                # 获取 README
                readme = self.crawler.get_readme(project['full_name'])
                
                # AI 分析
                analysis = self.analyzer.analyze_project(project, readme)
                self.db.update_ai_analysis(project['id'], analysis)
                
                results["analyze"] += 1
                self.progress["done"] += 1
                self._notify(f"Analyzed: {project['name']}", "success")
                
                # 避免 API 限制
                time.sleep(0.5)
            
            self._notify("Full scan completed!", "success")
            
            # Step 3: 自动归档数据到本地文件夹
            self.archive_data()
            
        except Exception as e:
            self._notify(f"Error during scan: {e}", "error")
            results["error"] = str(e)
        finally:
            self.is_running = False
            self.current_task = None
        
        return results
    
    def archive_data(self):
        """归档数据到本地文件夹"""
        import os
        import json
        
        date_str = datetime.now().strftime("%Y-%m-%d")
        archive_dir = f"data/archive/{date_str}"
        os.makedirs(archive_dir, exist_ok=True)
        
        self._notify(f"Archiving data to {archive_dir}...", "info")
        
        try:
            # 1. 导出所有数据
            all_projects = self.db.get_projects_by_category("all", limit=10000) # Hack to get all? No, need new DB method or iterate categories
            # Better: iterate categories
            
            summary_stats = {"total": 0, "breakdown": {}}
            
            for cat_id, cat_config in CATEGORIES.items():
                projects = self.db.get_projects_by_category(cat_id, limit=1000)
                if not projects:
                    continue
                    
                # 保存每个分类的 JSON
                file_path = f"{archive_dir}/{cat_id}.json"
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump([dict(p) for p in projects], f, ensure_ascii=False, indent=2)
                
                summary_stats["breakdown"][cat_id] = len(projects)
                summary_stats["total"] += len(projects)
            
            # 保存统计信息
            with open(f"{archive_dir}/_stats.json", 'w', encoding='utf-8') as f:
                json.dump(summary_stats, f, ensure_ascii=False, indent=2)
                
            self._notify(f"Data archived successfully to {archive_dir}", "success")
            
        except Exception as e:
            print(f"Archive error: {e}")
            self._notify(f"Archive error: {e}", "error")

    def run_batch_analysis(self) -> Dict:
        """批量分析所有未分析的项目 (使用快速模型)"""
        if self.is_running:
            return {"error": "Task already running"}
            
        self.is_running = True
        self.current_task = "batch_analysis"
        
        try:
            # 获取所有项目（可以稍微优化只获取未分析的，但为了演示效果，我们可以遍历所有没有 tutorial 的）
            # 或者只获取前 50 个未分析的
            pending = self.db.get_projects_needing_analysis(limit=100) # Increased limit
            
            self._notify(f"Starting batch analysis for {len(pending)} projects using Deepseek 8B...", "info")
            self.progress = {"total": len(pending), "done": 0, "current": "Batch Analysis"}
            
            analyzed_count = 0
            total = len(pending)
            
            for idx, project in enumerate(pending, 1):
                if not self.is_running: break # Allow cancellation (not implemented yet but good practice)
                
                progress_tag = f"[{idx}/{total}]"
                self.progress["current"] = f"Generating Tutorial: {project['name']}"
                self._notify(f"{progress_tag} 正在分析 {project['name']}...", "info")
                
                # 始终获取 README (教程生成需要)
                readme = self.crawler.get_readme(project['full_name'])
                
                # 1. 生成/更新 Analysis (如果缺失)
                if not project.get('ai_summary'):
                    analysis = self.analyzer.analyze_project(project, readme)
                    self.db.update_ai_analysis(project['id'], analysis)
                else:
                    analysis = {"summary": project.get('ai_summary')}
                
                if not project.get('ai_summary'):
                    analysis = self.analyzer.analyze_project(project, readme)
                    self.db.update_ai_analysis(project['id'], analysis)
                else:
                    analysis = {"summary": project.get('ai_summary')}
                
                # 1.1 生成 RAG Summary (如果缺失)
                if not project.get('ai_rag_summary'):
                    rag_summary = self.analyzer.generate_rag_summary(project, readme)
                    if rag_summary:
                        with self.db.lock:
                            self.db.conn.execute("UPDATE projects SET ai_rag_summary = ? WHERE id = ?", (rag_summary, project['id']))
                            self.db.conn.commit()
                
                # 2. 抓取截图 (如果缺失 或 强制更新)
                screenshot_path = project.get('screenshot')
                if not screenshot_path:
                    self._notify(f"{progress_tag} 正在截图 {project['name']}...", "info")
                    screenshot_path = self.crawler.capture_screenshot(project['url'], project['id'])
                    if screenshot_path:
                        self.db.update_screenshot(project['id'], screenshot_path)
                
                # 3. 视觉分析 (OCR & UI)
                visual_summary = ""
                if screenshot_path:
                    self._notify(f"{progress_tag} 视觉分析 (OCR) {project['name']}...", "info")
                    visual_summary = self.analyzer.analyze_with_vision(project, screenshot_path)
                    # Update DB with visual summary (need update method, handled in update_ai_analysis context or separate)
                    # Actually update_ai_analysis handles it if we pass it, but here we might want to attach it to 'analysis' dict
                    # Let's trust generate_tutorial uses it, and we save it too.
                    # We updated update_ai_analysis to take visual_summary key
                    if not analysis.get('visual_summary'):
                        analysis['visual_summary'] = visual_summary
                        self.db.update_ai_analysis(project['id'], analysis)

                # 4. 生成教程 (使用强力模型 + 视觉信息)
                self._notify(f"{progress_tag} 生成深度教程 (80B)...", "info")
                # Need to update generate_tutorial signature in master logic or calling
                # master.generate_tutorial calls self.content.generate_tutorial
                # Let's call content agent directly or update master.generate_tutorial signature?
                # Let's update master's generate_tutorial to accept visual_summary
                tutorial = self.content.generate_tutorial(project, readme, visual_summary)
                
                # Update DB
                with self.db.lock:
                    self.db.conn.execute("UPDATE projects SET ai_tutorial = ? WHERE id = ?", (tutorial, project['id']))
                    self.db.conn.commit()
                
                analyzed_count += 1
                self.progress["done"] += 1
                self._notify(f"{progress_tag} ✅ {project['name']} 教程生成完成", "success")
                
                # 稍微延时
                time.sleep(1)
            
            self._notify(f"🎉 批量分析完成！共处理 {analyzed_count} 个项目", "success")
            return {"status": "completed", "count": analyzed_count}
            
        except Exception as e:
            self._notify(f"Batch analysis error: {e}", "error")
            return {"error": str(e)}
        finally:
            self.is_running = False
            self.current_task = None

    def run_category_scan(self, category: str) -> Dict:
        """扫描单个分类"""
        if category not in CATEGORIES:
            return {"error": f"Unknown category: {category}"}
        
        cat_config = CATEGORIES[category]
        self._notify(f"Scanning {cat_config['name']}...", "info")
        
        if category == "trending":
            projects = self.crawler.get_trending()
        elif category == "new_releases":
            projects = self.crawler.get_new_releases()
        else:
            projects = self.crawler.search_by_keywords(cat_config["keywords"], category)
        
        for project in projects:
            self.db.upsert_project(project)
        
        self._notify(f"Found {len(projects)} projects", "success")
        return {"category": category, "count": len(projects)}
    
    def run_news_scan(self) -> Dict:
        """扫描每日发现源 (News Discovery)"""
        self.is_running = True
        self.current_task = "news_scan"
        results = {"total_found": 0, "sources": {}}
        
        try:
            self._notify("Starting News Discovery Scan...", "info")
            total_found = 0
            
            for url in DISCOVERY_URLS:
                self._notify(f"Crawling source: {url}...", "info")
                projects = self.crawler.crawl_external_page(url)
                
                # Assign to 'news' category if generic, or try to auto-classify later?
                # For now let's put them in 'news' category or 'manual'
                # The user asked for "continuous discovery", so maybe a 'news' category is best.
                # But our frontend needs to support 'news' category ID if we use it.
                # Let's check config.py... yes, 'news' category exists!
                
                source_count = 0
                for p in projects:
                    # 如果库里没有，才算新发现
                    if not self.db.get_project(p['id']):
                        p['category'] = 'news' # Force category
                        self.db.upsert_project(p)
                        source_count += 1
                        self._notify(f"Found new project: {p['name']}", "success")
                
                results["sources"][url] = source_count
                total_found += source_count
                
            self._notify(f"News Scan Completed. Found {total_found} new projects.", "success")
            results["total_found"] = total_found
            return results
            
        except Exception as e:
            self._notify(f"News scan error: {e}", "error")
            return {"error": str(e)}
        finally:
            self.is_running = False
            self.current_task = None

    def add_project_by_link(self, url: str) -> Dict:
        """从链接添加项目"""
        self._notify(f"Fetching project from {url}...", "info")
        project = self.crawler.fetch_project_by_url(url)
        
        if not project:
            return {"error": "Failed to fetch project. Check URL or network."}
        
        self.db.upsert_project(project)
        self._notify(f"Added {project['name']}. Starting analysis...", "success")
        
        # 立即分析
        threading.Thread(target=self.analyze_single, args=(project['id'],)).start()
        
        return {"status": "added", "project": project['name']}

    def reset_all_data(self) -> Dict:
        """重置所有数据"""
        try:
            self.db.clear_database()
            self._notify("Database cleared. All project data removed.", "warning")
            return {"status": "success", "message": "Database reset successfully"}
        except Exception as e:
            return {"error": str(e)}

    def analyze_single(self, project_id: str) -> Dict:
        """分析单个项目"""
        cursor = self.db.conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        )
        row = cursor.fetchone()
        if not row:
            return {"error": "Project not found"}
        
        project = dict(row)
        
        # 抓取截图
        if not project.get('screenshot'):
            screenshot_path = self.crawler.capture_screenshot(project['url'], project_id)
            if screenshot_path:
                self.db.update_screenshot(project_id, screenshot_path)
        
        readme = self.crawler.get_readme(project['full_name'])
        analysis = self.analyzer.analyze_project(project, readme)
        self.db.update_ai_analysis(project_id, analysis)
        
        # Generate RAG Summary
        rag_summary = self.analyzer.generate_rag_summary(project, readme)
        self.db.conn.execute("UPDATE projects SET ai_rag_summary = ? WHERE id = ?", (rag_summary, project_id))
        self.db.conn.commit()
        
        return analysis
    
    def generate_tutorial(self, project_id: str) -> str:
        """生成项目教程"""
        cursor = self.db.conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        )
        row = cursor.fetchone()
        if not row:
            return "Project not found"
        
        project = dict(row)
        readme = self.crawler.get_readme(project['full_name'])
        tutorial = self.content.generate_tutorial(project, readme)
        
        # 保存教程
        self.db.conn.execute(
            "UPDATE projects SET ai_tutorial = ? WHERE id = ?",
            (tutorial, project_id)
        )
        self.db.conn.commit()
        
        # 同时保存为 Markdown 文件
        try:
            timestamp = datetime.now().strftime("%Y%m%d")
            filename = f"data/tutorials/{project['name']}_{timestamp}.md"
            import os
            os.makedirs("data/tutorials", exist_ok=True)
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(tutorial)
        except:
            pass
        
        return tutorial
    
    def get_status(self) -> Dict:
        """获取当前状态"""
        return {
            "is_running": self.is_running,
            "current_task": self.current_task,
            "progress": self.progress,
            "categories": self.db.get_all_categories_summary()
        }
    
    
    def search_hybrid(self, query: str, limit: int = 20) -> Dict:
        """混合搜索：本地 DB + GitHub 实时搜索"""
        results = {"local": [], "remote": []}
        
        # 1. 本地搜索
        local_results = self.db.search_projects(query, limit=limit)
        results["local"] = local_results
        
        # 2. 如果本地结果很少，或者强制混合，则搜索 GitHub
        # 策略：本地不足 5 个，或者用户显式要求此功能
        if len(local_results) < 5:
            # 启动 GitHub 搜索 (注意这是一个阻塞操作，耗时约 1-2s)
            remote_results = self.crawler.search_remote(query, limit=10)
            
            # 去重：过滤掉已经在本地结果中的项目
            local_ids = {str(p['id']) for p in local_results}
            for p in remote_results:
                if str(p['id']) not in local_ids:
                    results["remote"].append(p)
                    
        return results

    def close(self):
        self.db.close()


def run_scheduled_scan(master: MasterAgent):
    """定时扫描任务 (后台线程)"""
    print("[Scheduler] Scheduler started.")
    
    last_run_date = None
    
    while True:
        try:
            now = datetime.now()
            # 获取设置的时间，默认 02:00
            scan_time_str = master.db.get_setting("scan_time", "02:00")
            try:
                target_hour, target_minute = map(int, scan_time_str.split(':'))
            except:
                target_hour, target_minute = 2, 0
            
            # 检查是否到达时间且今天未运行
            if now.hour == target_hour and now.minute == target_minute:
                today_str = now.strftime("%Y-%m-%d")
                if last_run_date != today_str:
                    print(f"[Scheduler] Starting scheduled scan at {scan_time_str}...")
                    master.run_full_scan()
                    last_run_date = today_str
                    time.sleep(65) # 避免这一分钟内重复触发
            
            time.sleep(30)
        except Exception as e:
            print(f"[Scheduler] Error: {e}")
            time.sleep(60)
