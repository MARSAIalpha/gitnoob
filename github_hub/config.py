# GitHub Hub - 开源项目智能仪表盘
# 配置文件

# ============================================================
# LM Studio 多模型配置
# ============================================================
LM_STUDIO_BASE = "http://198.18.0.1:1235/v1"
LM_STUDIO_KEY = "lm-studio"

MODELS = {
    "analyzer": "openai/gpt-oss-120b",      # 切换为 120B ChatGPTOss (速度更快)
    "classifier": "deepseek/deepseek-r1-0528-qwen3-8b",  # 快速分类
    "vision": "qwen/qwen3-vl-30b",          # 图像理解
}

# ============================================================
# 每日/每周发现源 (News Discovery)
# ============================================================
DISCOVERY_URLS = [
    # 示例: GitHub Trending, Weekly Blogs, Hacker News (需 Crawler 支持解析)
    # 目前仅作为示例配置，Crawler 将实现通用解析
    "https://github.com/trending",
    "https://github.com/trending?since=weekly",
]

# ============================================================
# GitHub API 配置
# ============================================================
GITHUB_API = "https://api.github.com"
GITHUB_TOKEN = None  # 可选，提高 API 限额

# ============================================================
# 项目分类配置
# ============================================================
CATEGORIES = {
    "llm_rag": {
        "name": "🧠 LLM & RAG",
        "keywords": ["llm", "langchain", "rag", "ollama", "llamaindex"],
        "description": "大模型应用与检索增强生成"
    },
    "ai_agent": {
        "name": "🤖 AI Agent",
        "keywords": ["ai-agent", "autogen", "crewai", "metagpt", "agentgpt"],
        "description": "智能体框架与自动化"
    },
    "multimodal": {
        "name": "🖼️ 多模态",
        "keywords": ["vision-language", "clip", "llava", "gpt4v", "multimodal"],
        "description": "图文理解与跨模态"
    },
    "image_gen": {
        "name": "🎨 图像生成",
        "keywords": ["stable-diffusion", "comfyui", "flux", "sdxl", "diffusers"],
        "description": "AI 绘图与图像生成"
    },
    "tts_voice": {
        "name": "🔊 语音合成",
        "keywords": ["tts", "voice-clone", "whisper", "so-vits", "bark"],
        "description": "文字转语音与声音克隆"
    },
    "digital_human": {
        "name": "👤 数字人",
        "keywords": ["digital-human", "talking-head", "wav2lip", "sadtalker"],
        "description": "虚拟人与唇形同步"
    },
    "mcp": {
        "name": "🔌 MCP 协议",
        "keywords": ["model-context-protocol", "mcp", "tool-use"],
        "description": "模型上下文协议与工具调用"
    },
    "devops": {
        "name": "🛠️ DevOps",
        "keywords": ["docker", "kubernetes", "cicd", "terraform", "ansible"],
        "description": "部署运维与基础设施"
    },
    "fullstack": {
        "name": "🌐 全栈框架",
        "keywords": ["nextjs", "nuxt", "remix", "astro", "sveltekit"],
        "description": "现代 Web 开发框架"
    },
    "ui_design": {
        "name": "🎨 UI 设计",
        "keywords": ["ui-design", "design-system", "component-library", "ui-kit", "tailwindcss", "css-animation"],
        "description": "UI 组件库与设计系统"
    },
    "video": {
        "name": "📹 视频处理",
        "keywords": ["video-editing", "ffmpeg", "bilibili", "youtube-dl", "yt-dlp"],
        "description": "视频下载与处理工具"
    },
    "news": {
        "name": "📰 信息聚合",
        "keywords": ["rss", "news-crawler", "readability", "feed"],
        "description": "新闻源与内容聚合"
    },
    "visualization": {
        "name": "📊 数据可视化",
        "keywords": ["dashboard", "chart", "grafana", "echarts"],
        "description": "数据展示与仪表盘"
    },
    "awesome": {
        "name": "📚 学习资源",
        "keywords": ["awesome", "roadmap", "interview", "tutorial"],
        "description": "精选列表与学习路径"
    },
    "trending": {
        "name": "🔥 Trending",
        "keywords": [],  # 使用 GitHub Trending API
        "description": "GitHub 热门趋势项目"
    },
    "new_releases": {
        "name": "🆕 新兴项目",
        "keywords": [],  # 按时间排序，stars > 100
        "description": "近期发布的高质量项目"
    },
    "manual": {
        "name": "🔧 手动添加",
        "keywords": [],
        "description": "手动添加的 GitHub 项目"
    }
}

import os
import shutil

# ============================================================
# 数据库配置
# ============================================================
if os.environ.get('VERCEL'):
    # Vercel Runtime: Use /tmp for writable SQLite
    DB_SOURCE = os.path.join(os.getcwd(), 'github_hub', 'data', 'projects.db')
    # If not found in primary location, try alternative structure (depending on deployment layout)
    if not os.path.exists(DB_SOURCE):
         DB_SOURCE = os.path.join(os.getcwd(), 'data', 'projects.db')
         
    DATABASE_PATH = "/tmp/projects.db"
    
    # Copy bundled DB to /tmp if not already there
    if not os.path.exists(DATABASE_PATH):
        try:
            if os.path.exists(DB_SOURCE):
                print(f"Copying DB from {DB_SOURCE} to {DATABASE_PATH}")
                shutil.copy2(DB_SOURCE, DATABASE_PATH)
            else:
                print(f"Warning: Source DB not found at {DB_SOURCE}, initializing empty.")
        except Exception as e:
            print(f"Error copying DB: {e}")
            
    print(f"Running on Vercel, using DB path: {DATABASE_PATH}")
else:
    # Local Development
    DATABASE_PATH = "data/projects.db"

# ============================================================
# 扫描配置
# ============================================================
SCAN_CONFIG = {
    "projects_per_category": 30,
    "min_stars": 100,
    "scan_interval_hours": 24,
}
