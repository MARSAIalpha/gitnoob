# GitHub Hub - GitHub API 爬虫 Agent
import requests
import time
import base64
import random
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from config import GITHUB_API, GITHUB_TOKEN, CATEGORIES, SCAN_CONFIG
import os

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None
    print("Warning: Playwright not found. Screenshot features disabled.")

class CrawlerAgent:
    """GitHub 爬虫 Agent - 负责获取项目信息、README 和截图"""
    
    def __init__(self):
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "GitHubHub-Agent/1.0"
        }
        if GITHUB_TOKEN:
            self.headers["Authorization"] = f"token {GITHUB_TOKEN}"
            
        # 确保截图目录存在
        os.makedirs("static/screenshots", exist_ok=True)

    def capture_screenshot(self, url: str, project_id: str) -> Optional[str]:
        """抓取网页截图 (滚动到 README 区域)"""
        if not sync_playwright:
             print("[Crawler] Playwright not installed, skipping screenshot.")
             return None
             
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(viewport={'width': 1280, 'height': 800})
                page.goto(url, timeout=30000)
                # 等待页面渲染
                page.wait_for_timeout(2000)
                
                # 尝试滚动到 README 区域 (GitHub 的 README 在 article 标签内)
                try:
                    readme_selector = 'article.markdown-body'
                    if page.locator(readme_selector).count() > 0:
                        page.locator(readme_selector).scroll_into_view_if_needed()
                        page.wait_for_timeout(500)
                except:
                    # 如果找不到 README，滚动到页面下方一点
                    page.evaluate('window.scrollBy(0, 400)')
                
                filename = f"static/screenshots/{project_id}.jpg"
                page.screenshot(path=filename, quality=80, type='jpeg')
                browser.close()
                return filename
        except Exception as e:
            print(f"[Crawler] Screenshot failed for {url}: {e}")
            return None
    
    def search_by_keywords(self, keywords: List[str], category: str, 
                           per_page: int = 30) -> List[Dict]:
        """按关键词搜索项目 (优化：合并关键词以减少 API 调用)"""
        
        # 将关键词合并为 "keyword1 OR keyword2 ..."
        # GitHub 限制 Query 长度，如果关键词太多可能需要分批，但一般 5-10 个没问题
        # 格式: (kw1 OR kw2) stars:>100
        
        joined_keywords = " OR ".join(keywords)
        query = f"({joined_keywords}) stars:>{SCAN_CONFIG['min_stars']}"
        
        url = f"{GITHUB_API}/search/repositories"
        params = {
            "q": query,
            "sort": "stars",
            "order": "desc",
            "per_page": min(per_page, 100)
        }
        
        print(f"[Crawler] Searching category '{category}' with query: {query[:50]}...")
        
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            
            # 处理速率限制
            if response.status_code == 403 or response.status_code == 429:
                print(f"[Crawler] Rate limit hit for {category}! Waiting 60s...")
                time.sleep(60)
                # 重试一次
                response = requests.get(url, headers=self.headers, params=params, timeout=30)
            
            response.raise_for_status()
            data = response.json()
            
            projects = []
            for item in data.get("items", []):
                projects.append(self._parse_repo(item, category))
                
            # 搜索 API 限制非常大 (10 req/min for unauth)，所以必须 sleep
            # 如果有 Token 可以快一点，如果没有建议 sleep 6s
            delay = 2 if GITHUB_TOKEN else 10
            time.sleep(delay)
            
            return projects
            
        except Exception as e:
            print(f"[Crawler] Error searching category '{category}': {e}")
            return []
    
    def search_remote(self, query: str, limit: int = 10) -> List[Dict]:
        """实时搜索 GitHub (Raw Project API) with Quality Filter & Pagination"""
        
        # 默认按相关性排序 (Best Match)，除非 Query 中指定了 sort
        base_params = {
            "q": query,
            "per_page": 50 # Increase fetch size to improve hit rate
        }
        
        if "sort:" in query:
             pass
        else:
             if "stars:" not in query:
                 base_params["q"] += " stars:>50"

        print(f"[Crawler] Remote search for: {base_params['q']}...")
        
        projects = []
        page = 1
        max_pages = 3 # Safety limit to prevent infinite loops
        
        # Local Quality Filter
        exclude_keywords = ["book", "interview", "tutorial", "course", "awesome", "collection", "list", "cheatsheet"]
        user_wants_tutorial = any(k in query.lower() for k in ["tutorial", "learn", "course", "book"])

        while len(projects) < limit and page <= max_pages:
            try:
                params = base_params.copy()
                params['page'] = page
                
                response = requests.get(f"{GITHUB_API}/search/repositories", headers=self.headers, params=params, timeout=15)
                
                if response.status_code in [403, 429]:
                    print(f"[Crawler] Rate limit hit for Remote Search!")
                    break
                
                response.raise_for_status()
                data = response.json()
                items = data.get("items", [])
                
                if not items:
                    break # No more results
                
                for item in items:
                    if len(projects) >= limit:
                        break
                        
                    # Filter 1: Exclude Spam/Books
                    if not user_wants_tutorial:
                        desc = (item.get("description") or "").lower()
                        name = item["name"].lower()
                        if any(bad in name or bad in desc for bad in exclude_keywords):
                            continue
                    
                    # Deduplication (Check if we already added this ID in this session)
                    if any(p['id'] == str(item['id']) for p in projects):
                        continue

                    p = self._parse_repo(item, "remote_search")
                    if not p.get('ai_rag_summary'):
                        p['ai_rag_summary'] = "GitHub Live Result"
                    projects.append(p)
                
                page += 1
                time.sleep(1) # Be nice to API
                
            except Exception as e:
                print(f"[Crawler] Error remote searching page {page}: {e}")
                break
                
        return projects
    
    def get_trending(self, since: str = "daily") -> List[Dict]:
        """获取 GitHub Trending 项目"""
        # GitHub 没有官方 Trending API，使用第三方或直接搜索热门
        url = f"{GITHUB_API}/search/repositories"
        params = {
            "q": f"stars:>1000 pushed:>{self._get_date_offset(7)}",
            "sort": "stars",
            "order": "desc",
            "per_page": 30
        }
        
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            return [self._parse_repo(item, "trending") for item in data.get("items", [])]
        except Exception as e:
            print(f"[Crawler] Error fetching trending: {e}")
            return []
    
    def get_new_releases(self) -> List[Dict]:
        """获取最近发布的高质量项目"""
        url = f"{GITHUB_API}/search/repositories"
        params = {
            "q": f"stars:>100 created:>{self._get_date_offset(30)}",
            "sort": "stars",
            "order": "desc",
            "per_page": 30
        }
        
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            return [self._parse_repo(item, "new_releases") for item in data.get("items", [])]
        except Exception as e:
            print(f"[Crawler] Error fetching new releases: {e}")
            return []
    
    def get_readme(self, full_name: str) -> Optional[str]:
        """获取项目 README 内容"""
        url = f"{GITHUB_API}/repos/{full_name}/readme"
        
        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            if response.status_code == 200:
                data = response.json()
                # README 内容是 base64 编码的
                import base64
                content = base64.b64decode(data.get("content", "")).decode("utf-8")
                return content[:10000]  # 限制长度
        except:
            pass
        return None

    def fetch_project_by_url(self, url: str) -> Optional[Dict]:
        """通过 URL 获取项目详情"""
        try:
            # Extract owner/repo from URL
            # https://github.com/owner/repo
            parts = url.rstrip('/').split('/')
            if len(parts) < 2:
                return None
            
            repo_full_name = f"{parts[-2]}/{parts[-1]}"
            
            api_url = f"{GITHUB_API}/repos/{repo_full_name}"
            response = requests.get(api_url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            return self._parse_repo(data, "manual") # 'manual' category
            
        except Exception as e:
            # Fallback: API Rate Limit or Network Error -> Try HTML Scrape
            if "403" in str(e) or "429" in str(e):
                print(f"[Crawler] Rate limit hit. Attempting HTML scrape fallback for {url}...")
                return self._scrape_github_page_fallback(url)
            
            print(f"[Crawler] Error fetching project by URL {url}: {e}")
            return None

    def _scrape_github_page_fallback(self, url: str) -> Optional[Dict]:
        """Github API 限流时的备用方案：直接爬取网页"""
        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract basic info from Meta Tags
            og_title = soup.find("meta", property="og:title")
            og_desc = soup.find("meta", property="og:description")
            
            full_name = og_title['content'].split(':')[0].strip() if og_title else "Unknown/Unknown"
            description = og_desc['content'] if og_desc else "No description available (Scraped)"
            
            # Helper to find number in text
            def parse_stars(text):
                import re
                match = re.search(r'([\d,]+\.?\d*[kK]?)', text)
                if not match: return 0
                val = match.group(1).replace(',', '')
                if 'k' in val.lower():
                    return int(float(val.lower().replace('k', '')) * 1000)
                return int(val)

            # Try to find Stars count (GitHub UI specific)
            stars = 0
            # Strategy: Find "Star" button -> count
            # This is fragile, so we might just use 0 or default
            star_span = soup.find("span", id="repo-stars-counter-star")
            if star_span:
                stars = parse_stars(star_span.get_text())
                
            return {
                "id": str(hash(full_name)), # Mock ID
                "name": full_name.split('/')[-1],
                "full_name": full_name,
                "description": description,
                "stars": stars,
                "language": "Unknown (Scraped)", # Hard to parse reliably
                "url": url,
                "category": "manual_scraped",
                "topics": ["scraped"],
                "created_at": "2024-01-01T00:00:00Z", # Mock
                "pushed_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "readme": "HTML Scraped - Pending AI Analysis"
            }
        except Exception as e:
            print(f"[Crawler] HTML Scrape failed: {e}")
            return None
    
    def _parse_repo(self, item: Dict, category: str) -> Dict:
        """解析仓库数据"""
        return {
            "id": str(item["id"]),
            "name": item["name"],
            "full_name": item["full_name"],
            "category": category,
            "stars": item["stargazers_count"],
            "forks": item["forks_count"],
            "description": item.get("description", ""),
            "url": item["html_url"],
            "homepage": item.get("homepage"),
            "language": item.get("language"),
            "topics": item.get("topics", []),
            "created_at": item["created_at"],
            "updated_at": item["updated_at"],
        }
    
    def _get_date_offset(self, days: int) -> str:
        """获取 N 天前的日期"""
        from datetime import datetime, timedelta
        date = datetime.now() - timedelta(days=days)
        return date.strftime("%Y-%m-%d")
    
    def crawl_all_categories(self, db) -> Dict:
        """爬取所有分类"""
        results = {}
        
        for cat_id, cat_config in CATEGORIES.items():
            print(f"[Crawler] Scanning category: {cat_config['name']}")
            
            if cat_id == "trending":
                projects = self.get_trending()
            elif cat_id == "new_releases":
                projects = self.get_new_releases()
            else:
                projects = self.search_by_keywords(cat_config["keywords"], cat_id)
            
            # 存入数据库
            new_count = 0
            for project in projects:
                db.upsert_project(project)
                new_count += 1
            
            db.log_scan(cat_id, len(projects), new_count, "success")
            results[cat_id] = len(projects)
            print(f"[Crawler] Found {len(projects)} projects in {cat_config['name']}")
        
        return results
    
    def crawl_external_page(self, url: str) -> List[Dict]:
        """爬取外部网页 (如周报、Trending) 中的 GitHub 项目链接"""
        print(f"[Crawler] Scanning external source: {url}")
        projects = []
        try:
            # 简单请求网页
            response = requests.get(url, headers=self.headers, timeout=15)
            if response.status_code != 200:
                print(f"[Crawler] Failed to load {url}: {response.status_code}")
                return []
                
            # 解析 HTML，提取所有 github.com/user/repo 格式链接
            from bs4 import BeautifulSoup
            import re
            
            soup = BeautifulSoup(response.text, 'html.parser')
            # 查找所有 a 标签
            links = soup.find_all('a', href=True)
            
            seen_repos = set()
            
            for link in links:
                href = link['href']
                # 匹配 github.com/owner/repo (且不包含 issues, pulls 等)
                # 优化正则：排除 common false positives
                match = re.search(r'github\.com/([a-zA-Z0-9._-]+)/([a-zA-Z0-9._-]+)', href)
                if match:
                    full_name = f"{match.group(1)}/{match.group(2)}"
                    
                    # 过滤: 排除自己, 排除常见非项目路径
                    if full_name in seen_repos: continue
                    if any(x in full_name.lower() for x in ['site/policy', 'login', 'pricing', 'features', 'topics/', 'search', 'about', 'contact']): continue
                    
                    seen_repos.add(full_name)
                    
                    # 获取链接文本作为简单描述
                    link_text = link.get_text().strip()
                    if not link_text or "github.com" in link_text:
                        # 尝试获取父级上下文? 暂时先留空
                        link_text = "Discovered via link"
                    
                    print(f"[Crawler] Found repo link: {full_name}")
                    
                    # Lightweight Item
                    projects.append({
                        "id": str(hash(full_name)),
                        "name": full_name.split('/')[-1],
                        "full_name": full_name,
                        "description": f"Found in {url}. Link text: {link_text[:50]}...",
                        "stars": 0, # Unknown
                        "language": "Unknown",
                        "url": f"https://github.com/{full_name}",
                        "category": "news", # 标记为新闻发现
                        "topics": ["discovered"],
                        "created_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "ai_rag_summary": "Click 'Save' to fetch details"
                    })
                    
                    # Limit
                    if len(projects) >= 30: break 
                        
            return projects
            
        except Exception as e:
            print(f"[Crawler] Error scanning external page {url}: {e}")
            return []
