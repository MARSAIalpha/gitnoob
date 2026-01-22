# GitHub Hub - Flask Web Server
from flask import Flask, jsonify, request, send_from_directory, Response
from flask_cors import CORS
import json
import queue
import threading
from master import MasterAgent
from config import CATEGORIES

app = Flask(__name__, static_folder='static')
CORS(app)

# 全局 Master Agent
master = MasterAgent()

# SSE 日志队列
log_queue = queue.Queue()

def log_callback(data):
    """日志回调，推送到 SSE 队列"""
    log_queue.put(data)

master.add_callback(log_callback)


@app.route('/')
def index():
    """主页"""
    import os
    # Use absolute path resolution
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return send_from_directory(base_dir, 'dashboard.html')


@app.route('/api/categories')
def get_categories():
    """获取所有分类配置"""
    return jsonify(CATEGORIES)


@app.route('/api/projects/<category>')
def get_projects(category):
    """获取某分类的项目列表"""
    limit = request.args.get('limit', 100, type=int)
    projects = master.db.get_projects_by_category(category, limit)
    
    # Supabase JSONB fields are already Python objects, no parsing needed
    return jsonify(projects)

@app.route('/api/export')
def export_data():
    """导出所有数据到 JSON"""
    try:
        projects = master.db.get_all_projects()
        
        # 解析 JSON 字段
        for p in projects:
            for field in ['topics', 'ai_tech_stack', 'ai_use_cases']:
                if p.get(field):
                    try:
                        p[field] = json.loads(p[field])
                    except:
                        p[field] = []
        
        # 保存到文件
        export_path = "github_projects_export.json"
        with open(export_path, 'w', encoding='utf-8') as f:
            json.dump(projects, f, ensure_ascii=False, indent=2)
            
        return jsonify({
            "status": "success", 
            "message": f"已导出 {len(projects)} 个项目到 {export_path}",
            "path": export_path,
            "count": len(projects)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/project/<project_id>')
def get_project(project_id):
    """获取单个项目详情"""
    project = master.db.get_project(project_id)
    if not project:
        return jsonify({"error": "Not found"}), 404
    # 解析 JSON 字段
    for field in ['topics', 'ai_tech_stack', 'ai_use_cases']:
        if project.get(field):
            try:
                project[field] = json.loads(project[field])
            except:
                project[field] = []
    
    return jsonify(project)


@app.route('/api/scan', methods=['POST'])
def start_scan():
    """启动完整扫描"""
    if master.is_running:
        return jsonify({"error": "Scan already running"}), 400
    
    # 在后台线程运行
    thread = threading.Thread(target=master.run_full_scan)
    thread.daemon = True
    thread.start()
    
    return jsonify({"status": "started"})

@app.route('/api/stop', methods=['POST'])
def stop_process():
    """停止当前任务"""
    result = master.stop_task()
    return jsonify(result)


@app.route('/api/scan/<category>', methods=['POST'])
def scan_category(category):
    """扫描单个分类"""
    result = master.run_category_scan(category)
    return jsonify(result)


@app.route('/api/settings', methods=['GET'])
def get_settings():
    """获取所有设置"""
    # 目前只有 scan_time
    scan_time = master.db.get_setting("scan_time", "02:00")
    return jsonify({"scan_time": scan_time})

@app.route('/api/settings', methods=['POST'])
def save_settings():
    """保存设置"""
    data = request.json
    scan_time = data.get('scan_time')
    if scan_time:
        master.db.set_setting("scan_time", scan_time)
        return jsonify({"status": "saved", "scan_time": scan_time})
    return jsonify({"error": "Invalid data"}), 400

@app.route('/api/scan/news', methods=['POST'])
def scan_news():
    """手动触发新闻源扫描"""
    if master.is_running:
        return jsonify({"error": "Scan already running"}), 400
    
    # 在后台线程运行
    thread = threading.Thread(target=master.run_news_scan)
    thread.daemon = True
    thread.start()
    
    return jsonify({"status": "started", "message": "News scan started"})


@app.route('/api/analyze/<project_id>', methods=['POST'])
def analyze_project(project_id):
    """分析单个项目"""
    result = master.analyze_single(project_id)
    return jsonify(result)


@app.route('/api/analyze_all', methods=['POST'])
def analyze_all():
    """触发批量分析"""
    threading.Thread(target=master.run_batch_analysis).start()
    return jsonify({"status": "started", "message": "Batch analysis started in background"})

@app.route('/api/search', methods=['POST'])
def search_agent():
    """智能搜索 Agent"""
    data = request.json
    query = data.get('query', '')
    if not query:
        return jsonify({"error": "Query is required"}), 400
        
    # 1. 混合检索
    master._notify(f"🔍 Searching local database for '{query}'...", "info")
    search_result = master.search_hybrid(query, limit=20)
    results = search_result["local"] + search_result["remote"]
    
    # 2. AI 推荐 (如有结果)
    recommendation = ""
    # 如果请求 skip_ai，则跳过推荐生成
    if not data.get('skip_ai'):
        if results:
            master._notify(f"🧠 Found {len(results)} projects. AI Analyst is generating recommendation...", "info")
            recommendation = master.content.recommend_solution(query, results)
        else:
            recommendation = "抱歉，数据库中暂时没有找到匹配的项目。建议尝试其他关键词，或先进行更多类别的扫描。"
    else:
        master._notify(f"✅ Fast search completed! Found {len(results)} projects.", "success")
        
    master._notify("✅ Search completed!", "success")
    return jsonify({
        "results": results,
        "recommendation": recommendation
    })

@app.route('/api/agent/refine', methods=['POST'])
def refine_agent():
    """对话式搜索意图优化"""
    data = request.json
    history = data.get('history', [])
    
    # 使用 Analyzer 的 refinement 逻辑
    result = master.analyzer.refine_search_intent(history)
    return jsonify(result)

@app.route('/api/search/local', methods=['POST'])
def search_local():
    """快速本地搜索"""
    data = request.json
    query = data.get('query', '')
    limit = data.get('limit', 20)
    
    results = master.db.search_projects(query, limit=limit)
    return jsonify({"results": results})

@app.route('/api/search/remote', methods=['POST'])
def search_remote():
    """GitHub 远程搜索 (较慢)"""
    data = request.json
    query = data.get('query', '')
    limit = data.get('limit', 10)
    
    results = master.crawler.search_remote(query, limit=limit)
    return jsonify({"results": results})

@app.route('/api/search/recommend', methods=['POST'])
def recommend_agent():
    """单独生成 AI 推荐"""
    data = request.json
    query = data.get('query', '')
    projects = data.get('projects', [])
    
    if not query or not projects:
        return jsonify({"error": "Query and projects are required"}), 400
        
    master._notify(f"🧠 AI Analyst is analyzing {len(projects)} projects for recommendation...", "info")
    recommendation = master.content.recommend_solution(query, projects)
    master._notify("✅ Recommendation generated!", "success")
    
    return jsonify({
        "recommendation": recommendation
    })

@app.route('/api/news/scan', methods=['POST'])
def scan_news_source():
    """扫描外部网页寻找 GitHub 链接"""
    data = request.json
    url = data.get('url', '')
    if not url:
        return jsonify({"error": "URL is required"}), 400
        
    master._notify(f"🌍 Scanning news source: {url} ...", "info")
    projects = master.crawler.crawl_external_page(url)
    master._notify(f"✅ Found {len(projects)} potential projects.", "success")
    
    
    return jsonify({"results": projects})

@app.route('/api/news/sources', methods=['GET'])
def get_news_sources():
    """获取所有新闻源"""
    sources = master.db.get_news_sources()
    return jsonify({"sources": sources})

@app.route('/api/news/sources/add', methods=['POST'])
def add_news_source():
    """添加新闻源"""
    data = request.json
    name = data.get('name', 'Untitled Source')
    url = data.get('url', '')
    if not url: return jsonify({"error": "URL required"}), 400
    
    master.db.add_news_source(name, url)
    return jsonify({"status": "added"})

@app.route('/api/news/sources/delete/<int:id>', methods=['DELETE'])
def delete_news_source(id):
    """删除新闻源"""
    master.db.delete_news_source(id)
    return jsonify({"status": "deleted"})

@app.route('/api/news/sources/scan/<int:id>', methods=['POST'])
def scan_specific_news_source(id):
    """扫描特定新闻源并入库"""
    # 1. Get URL
    sources = master.db.get_news_sources()
    target = next((s for s in sources if s['id'] == id), None)
    if not target: return jsonify({"error": "Source not found"}), 404
    
    master._notify(f"🌍 Scanning source: {target['name']}...", "info")
    
    # 2. Crawl
    projects = master.crawler.crawl_external_page(target['url'])
    
    # 3. Filter Duplicates (Already in DB?)
    new_items = []
    for p in projects:
        # Check by full_name usually, but we only have URL/Name in lightweight items
        # crawler now returns basics.
        # We can check if ID exists (hash of fullname)
        if not master.db.project_exists(p['id']):
             new_items.append(p)
    
    # 4. Update Scan Time
    master.db.update_news_source_scan_time(id)
    
    master._notify(f"✅ Source scanned. Found {len(new_items)} new items.", "success")
    return jsonify({"results": new_items, "total_found": len(projects), "new_count": len(new_items)})

@app.route('/api/project/add', methods=['POST'])
def add_project_link():
    """手动添加项目链接"""
    data = request.json
    url = data.get('url', '')
    if not url:
        return jsonify({"error": "URL is required"}), 400
        
    result = master.add_project_by_link(url)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)

@app.route('/api/reset', methods=['POST'])
def reset_system():
    """重置系统数据"""
    result = master.reset_all_data()
    if "error" in result:
        return jsonify(result), 500
    return jsonify(result)

@app.route('/api/project/delete/<project_id>', methods=['DELETE'])
def delete_project(project_id):
    """删除单个项目"""
    try:
        master.db.delete_project(project_id)
        return jsonify({"status": "deleted", "id": project_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/tutorial/<project_id>')
def get_tutorial(project_id):
    """获取或生成项目教程"""
    existing_tutorial = master.db.get_tutorial(project_id)
    
    if existing_tutorial:
        return jsonify({"tutorial": existing_tutorial})
    
    # 生成新教程
    tutorial = master.generate_tutorial(project_id)
    return jsonify({"tutorial": tutorial})


@app.route('/api/status')
def get_status():
    """获取系统状态"""
    return jsonify(master.get_status())


@app.route('/api/stats')
def get_stats():
    """获取统计信息"""
    return jsonify(master.db.get_stats())

@app.route('/api/pending')
def get_pending():
    """获取待分析项目数量"""
    count = master.db.get_pending_count()
    return jsonify({"pending": count})

@app.route('/api/progress')
def get_progress():
    """获取当前分析进度"""
    return jsonify(master.progress if hasattr(master, 'progress') else {"total": 0, "done": 0, "current": "Idle"})


@app.route('/api/logs')
def stream_logs():
    """SSE 日志流"""
    def generate():
        while True:
            try:
                data = log_queue.get(timeout=30)
                yield f"data: {json.dumps(data)}\n\n"
            except:
                yield f"data: {json.dumps({'message': 'ping', 'level': 'ping'})}\n\n"
    
    return Response(generate(), mimetype='text/event-stream')


if __name__ == '__main__':
    print("\n" + "="*60)
    print("=== GitHub Hub - Open Source Project Dashboard ===")
    print("="*60)
    print("Open: http://localhost:5001")
    print("API:  http://localhost:5001/api/status")
    print("="*60 + "\n")
    
    # 启动定时任务线程
    from master import run_scheduled_scan
    scheduler_thread = threading.Thread(target=run_scheduled_scan, args=(master,))
    scheduler_thread.daemon = True
    scheduler_thread.start()
    
    app.run(host='0.0.0.0', port=5001, debug=True, threaded=True)
