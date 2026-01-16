# GitHub Hub - AI 分析 Agent
from openai import OpenAI
from typing import Dict, List, Optional
import json
from config import LM_STUDIO_BASE, LM_STUDIO_KEY, MODELS

class AnalyzerAgent:
    """AI 分析 Agent - 使用本地 LM Studio 模型"""
    
    def __init__(self):
        try:
            self.client = OpenAI(base_url=LM_STUDIO_BASE, api_key=LM_STUDIO_KEY)
        except Exception as e:
            print(f"Warning: Could not initialize OpenAI client: {e}")
            self.client = None
    
    def analyze_project(self, project: Dict, readme: Optional[str] = None) -> Dict:
        """分析单个项目，生成 Metadata"""
        
        context = f"""
项目名称: {project['name']}
完整名称: {project['full_name']}
描述: {project.get('description', '无')}
语言: {project.get('language', '未知')}
星标: {project['stars']}
Topics: {', '.join(project.get('topics', []))}
"""
        if readme:
            context += f"\n\nREADME 内容 (前3000字):\n{readme[:3000]}"
        
        prompt = f"""请分析以下 GitHub 开源项目，并以 JSON 格式返回分析结果：

{context}

请返回以下 JSON 格式（确保是有效的 JSON）：
{{
    "summary": "一句话精准概括：这是做什么的+核心技术特点+独特优势。例如：'基于LangChain的多Agent对话系统，支持插件式工具调用和长期记忆'",
    "tech_stack": ["核心技术栈，如 LangChain, FastAPI, ChromaDB 等"],
    "use_cases": ["具体应用场景1", "场景2", "场景3"],
    "difficulty": 1-5 的数字,
    "highlights": ["技术亮点1", "亮点2"],
    "ai_tags": ["3-5个最能描述项目功能特点的关键词，如 '多模态', 'RAG检索', '流式对话', '代码生成', '知识库' - 不要用太宽泛的词如 'AI', 'Python'"],
    "quick_start": "快速启动命令"
}}

只返回 JSON，不要添加其他文字。"""

        try:
            if not self.client:
                return self._default_analysis(project)
            response = self.client.chat.completions.create(
                model=MODELS["classifier"],  # 使用快速模型
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=1000
            )
            
            content = response.choices[0].message.content.strip()
            # 提取 JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            return json.loads(content)
            
        except json.JSONDecodeError as e:
            print(f"[Analyzer] JSON parse error for {project['name']}: {e}")
            return self._default_analysis(project)
        except Exception as e:
            print(f"[Analyzer] Error analyzing {project['name']}: {e}")
            return self._default_analysis(project)
    
    def generate_rag_summary(self, project: Dict, readme: Optional[str] = None) -> str:
        """生成面向 RAG 的高密度总结 (给 LLM 看的)"""
        context = f"项目: {project['full_name']}\n描述: {project.get('description', '')}\nTopics: {project.get('topics', [])}"
        if readme:
            context += f"\nREADME extract: {readme[:2000]}"
            
        prompt = f"""请为以下 GitHub 项目生成一段**面向 LLM 的高密度总结** (RAG Summary)。
目标：当用户提问时，搜索引擎可以通过这段总结快速判断该项目是否符合用户需求。

{context}

要求：
1. **高度浓缩**：不要废话，直接列出核心功能。
2. **场景导向**：明确指出"适合做什么" (Ideal for...)。
3. **技术关键词**：包含关键架构、依赖库、算法名词。
4. **优缺点**：简要提及潜在限制。
5. **格式**：纯文本，不要 Markdown 格式，控制在 150 字以内。

示例格式：
"[Python] 基于FastAPI的异步Web框架。核心优势是高性能和自动文档生成。适合构建高并发微服务。依赖uvicorn。不支持Python 3.6以下。类似Flask但更快。"
"""
        try:
            response = self.client.chat.completions.create(
                model=MODELS["classifier"], # Use fast model
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=300
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"[Analyzer] RAG summary failed: {e}")
            return project.get('description', '')
    
    def _default_analysis(self, project: Dict) -> Dict:
        """默认分析结果"""
        return {
            "summary": project.get('description', '暂无描述'),
            "tech_stack": [project.get('language', 'Unknown')],
            "use_cases": ["通用开发"],
            "difficulty": 3,
            "quick_start": f"git clone {project['url']}"
        }
    
    def classify_project(self, project: Dict, categories: List[str]) -> str:
        """自动分类项目"""
        prompt = f"""请判断以下项目最适合哪个分类：

项目: {project['name']}
描述: {project.get('description', '无')}
语言: {project.get('language', '未知')}
Topics: {', '.join(project.get('topics', []))}

可选分类: {', '.join(categories)}

只返回一个分类名称，不要其他文字。"""

        try:
            response = self.client.chat.completions.create(
                model=MODELS["classifier"],
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=50
            )
            return response.choices[0].message.content.strip()
        except:
            return "awesome"  # 默认归类到学习资源

    def refine_search_intent(self, history: List[Dict]) -> Dict:
        """根据对话历史优化搜索意图"""
        
        # 构建对话上下文
        conversation = ""
        for msg in history[-5:]: # 取最近5轮
            role = "User" if msg['role'] == 'user' else "Assistant"
            conversation += f"{role}: {msg['content']}\n"
            
        prompt = f"""你是一个**严谨的需求分析师**。你的任务是辅助用户精确定义 GitHub 搜索需求。

**核心原则：绝不轻易搜索**。
绝大多数用户的初始描述都是模糊的（例如 "找个爬虫"）。你的工作是像并在**开始搜索前**，必须收集齐以下 **3 个关键要素**：

1. **核心技术栈 (Tech Stack)**: 必须明确语言（如 Python/Go/Rust）或特定框架（如 React/Next.js）。
2. **应用场景 (Context)**: 是要一个**开箱即用的工具 (Application)**，还是**开发者库 (Library/SDK)**？或是**学习教程 (Tutorial)**？
3. **关键特性 (Key Features)**: 具体的差异化需求（例如 "支持分布式"、"带有 Web UI"、"轻量级"）。

---
**决策流程**:

**情况 A: 信息缺失 (Action: question)**
如果上述 3 个要素中有**任意一个**不明确：
- **必须**提出针对性的问题。
- 一次只问 1-2 个最重要的问题，不要一次性抛出太多。
- 语气要专业、引导性强。

**情况 B: 信息完备 (Action: search)**
只有当用户已经明确提供了所有要素，或者用户显式要求 "直接搜" 时：
- 生成精准的 GitHub Search Query。
- 必须包含 `language:` 和 `topic:` 过滤器。

---
**示例**:

**场景 1 (信息极缺)**
User: "想要个后台管理"
Assistant: JSON {{ "action": "question", "content": "后台管理系统有很多种。请问您是偏好 **Java (Spring Boot)**, **Python (Django/FastAPI)** 还是 **Node.js**？另外，您是需要一套**现成的 Admin UI** 还是要一个**后端框架**？", "reasoning": "缺少技术栈和类型" }}

**场景 2 (缺少场景)**
User: "Python 爬虫"
Assistant: JSON {{ "action": "question", "content": "收到。请问您是想找一个**开箱即用的爬虫软件**（如直接爬各种网站的工具），还是需要一个**Python 开发库**（如 Scrapy/Playwright）来自己写代码？", "reasoning": "不确定是工具还是库" }}

**场景 3 (缺少特性)**
User: "Python 写的爬虫库，用来爬新闻"
Assistant: JSON {{ "action": "question", "content": "了解。针对新闻爬取，您是否需要支持**异步 (Async)**？或者是否需要**自动处理反爬虫 (Anti-detect)** 的功能？", "reasoning": "尝试挖掘高级特性" }}

**场景 4 (完备)**
User: "Python 异步新闻爬虫，支持反爬"
Assistant: JSON {{ "action": "search", "content": "news crawler language:python topic:asyncio topic:anti-detect pushed:>2023-01-01", "reasoning": "要素齐备" }}

请分析以下对话，返回 JSON:"""

        try:
            response = self.client.chat.completions.create(
                model=MODELS["classifier"], # 使用快速模型
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=200
            )
            content = response.choices[0].message.content.strip()
            # Clean JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
                
            return json.loads(content)
        except Exception as e:
            print(f"[Analyzer] Refine intent failed: {e}")
            # Fallback to search if error
            last_user_msg = next((m['content'] for m in reversed(history) if m['role'] == 'user'), "")
            return {"action": "search", "content": last_user_msg, "reasoning": "Fallback"}

    def analyze_with_vision(self, project: Dict, image_path: str) -> str:
        """使用视觉模型分析截图 (OCR & UI理解)"""
        import base64
        
        try:
            with open(image_path, "rb") as image_file:
                base64_image = base64.b64encode(image_file.read()).decode('utf-8')
                
            prompt = f"""请仔细观察这张 GitHub 项目的截图 (OCR)：
            
项目: {project['name']}
描述: {project.get('description', '')}

请提取图中的关键文本信息，并分析 UI/界面 设计风格。
重点关注：
1. 界面主要功能模块
2. 任何可见的技术关键词
3. 这个应用看起来是做什么的？

请用一段简短的中文总结你的视觉分析结果。"""

            response = self.client.chat.completions.create(
                model=MODELS["vision"], 
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=500
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"[Analyzer] Vision analysis failed: {e}")
            return "视觉分析失败"


class ContentAgent:
    """内容生成 Agent - 生成教程和文档"""
    
    def __init__(self):
        try:
            self.client = OpenAI(base_url=LM_STUDIO_BASE, api_key=LM_STUDIO_KEY)
        except Exception as e:
            print(f"Warning: Could not initialize ContentAgent OpenAI client: {e}")
            self.client = None
    
    
    def generate_tutorial(self, project: Dict, readme: Optional[str] = None, visual_summary: str = "") -> str:
        """生成项目教程 (使用强力模型)"""
        
        context = f"""
项目: {project['full_name']}
描述: {project.get('description', '')}
语言: {project.get('language', '')}
星标: {project['stars']}
"""
        if readme:
            context += f"\nREADME (部分):\n{readme[:4000]}"
            
        if visual_summary:
            context += f"\n\nUI/界面视觉分析 (OCR):\n{visual_summary}"
        
        prompt = f"""你是一位资深架构师。目标读者是**有经验的开发者**，请跳过基础概念解释（如"什么是AI Agent"、"什么是RAG"等）。直接分析这个项目的**独特价值和技术实现细节**。

{context}

CRITICAL: 直接输出 Markdown 内容，不要有任何开场白（如“当然可以”、“好的”、“这是为您生成的...”等），也不要有结束语。直接开始教程内容。

## 📚 教程结构要求（请严格按此格式输出）：

### 🎯 核心价值 & 差异化
(这个项目和同类项目相比，**独特在哪里**？解决了什么别人没解决好的问题？)

### 🔥 技术亮点
(这个项目有什么**值得学习的技术实现**？比如：
- 某个巧妙的算法设计
- 独特的架构选择
- 性能优化手段)

### 🏗️ 架构设计分析
(这是**进阶**内容，请分析：
1. 项目的整体架构图（用文字描述或 ASCII 图）
2. 核心模块划分和职责
3. 数据流向（输入 → 处理 → 输出）
4. 关键设计模式：用了什么设计模式？为什么这么设计？)

### 🔧 技术栈深度解析
(不只是列出技术栈，要解释：
- 为什么选择这个技术？有什么替代方案？
- 核心依赖库的作用是什么？
- 版本兼容性注意事项)

### 📦 安装与配置
(提供复制粘贴的命令 + 每步注释)

### 🎮 使用示例
(提供一个**完整的代码示例**，包含：
- 真实场景的输入
- 预期输出
- 关键参数说明)

### ⚡ 性能与优化
(分析或推测：
- 性能瓶颈在哪？
- 如何扩展到生产环境？
- 资源消耗估算)

### 🔌 二次开发指南
(如何基于这个项目进行改造？
- 关键的扩展点
- API 接口说明
- 如何添加自定义功能)

### ❗ 常见问题与避坑
(列出 5+ 个常见问题，附解决方案)

### 🚀 进阶学习路径
(学完这个后的下一步是什么？相关项目推荐)
"""

        try:
            # 使用强力模型 (Analyzer/80B) 生成高质量教程
            response = self.client.chat.completions.create(
                model=MODELS["analyzer"], # Switch to Strongest Model
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=3000
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"[Content] Error generating tutorial for {project['name']}: {e}")
            return f"# {project['name']}\n\n{project.get('description', '暂无教程')}"
    
    def compare_projects(self, projects: List[Dict]) -> str:
        """对比多个同类项目"""
        
        project_list = "\n".join([
            f"- {p['name']}: {p.get('description', '')} (⭐ {p['stars']})"
            for p in projects[:5]
        ])
        
        prompt = f"""请对比以下同类开源项目，分析各自的优缺点和适用场景：

{project_list}

请用表格形式对比，包括：功能特点、性能、易用性、社区活跃度、适合的使用场景。"""

        try:
            response = self.client.chat.completions.create(
                model=MODELS["analyzer"],
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
                max_tokens=2000
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"[Content] Error comparing projects: {e}")
            return "对比生成失败"

    def recommend_solution(self, query: str, search_results: List[Dict]) -> str:
        """根据搜索结果推荐解决方案"""
        
        context = "\n".join([
            f"{i+1}. {p['name']} (⭐ {p['stars']}):\n   Summary: {p.get('ai_rag_summary') or p.get('description', '')}\n   Tags: {', '.join(p.get('topics', [])[:5])}"
            for i, p in enumerate(search_results[:8])
        ])
        
        prompt = f"""用户正在寻找解决以下问题的方案：
"{query}"

基于已有的 GitHub 项目库，我找到了以下相关项目：
{context}

请扮演一位资深架构师，为用户推荐最佳的技术选型方案。
回答要求：
1. **直接推荐**：最推荐哪个项目？为什么？
2. **方案对比**：如果还有其他选择，它们的优缺点是什么？
3. **实施建议**：如何组合使用这些工具？
4. **不足之处**：如果没有完美的匹配，目前方案的局限性是什么？

请保持客观、专业，语气亲切。"""

        try:
            response = self.client.chat.completions.create(
                model=MODELS["analyzer"], # Use Strong Model
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
                max_tokens=1500
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"[Content] Error recommending solution: {e}")
            return "推荐生成失败"
