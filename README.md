# SmartNotes - AI 智能笔记助手

基于多 Agent 架构的 AI 驱动笔记管理平台，集成笔记整理、智能问答、复习计划生成和知识库管理功能，支持流式输出和多用户隔离。

## 功能特性

- **笔记整理 Agent** - 将原始笔记智能整理为结构化格式，支持自定义风格
- **复习计划 Agent** - 基于艾宾浩斯遗忘曲线生成科学的复习计划
- **问答 Agent (ReAct)** - 支持工具调用的智能问答，可检索个人知识库
- **企业级 RAG 知识检索** - Query 改写、数据清洗、智能切片、混合召回、MMR 重排
- **知识库管理** - 支持文本/文件上传，向量检索，用户数据隔离
- **统一网关** - JWT 认证、Redis 滑动窗口限流、请求路由转发
- **流式输出** - 所有 AI 功能均支持 SSE 流式响应

## 技术架构

### 后端技术栈

| 组件 | 技术 |
|------|------|
| Web 框架 | FastAPI + Uvicorn |
| AI 框架 | LangChain + LangChain-OpenAI |
| LLM 服务 | 阿里云百炼 Qwen3.7-plus |
| Embedding | 阿里云百炼 text-embedding-v3 |
| 数据库 | MySQL 8.0 (SQLAlchemy 2.0 + aiomysql) |
| 缓存/会话 | Redis 6.2 |
| 向量数据库 | ChromaDB |
| 认证 | JWT + bcrypt |

### 前端技术栈

| 组件 | 技术 |
|------|------|
| 框架 | Vue 3 + Vite |
| UI 组件库 | Element Plus |
| 状态管理 | Pinia |
| HTTP 客户端 | Axios |
| 路由 | Vue Router |

### 微服务架构

```
                    +------------+
                    |   Nginx    |
                    |  (前端静态)  |
                    +-----+------+
                          |
                    +-----v------+
                    |  Gateway   |  <-- JWT认证、限流、路由
                    |   :8000    |
                    +-----+------+
                          |
        +-----------------+-----------------+
        |                 |                 |
  +-----v-----+    +------v-----+    +-----v-----+
  | Agent Note|    | Agent Plan |    | Agent QA  |
  |  :8001    |    |   :8002    |    |  :8003    |
  +-----------+    +------------+    +-----------+
        |                 |                 |
        +-----------------+-----------------+
                          |
              +-----------+-----------+
              |                       |
        +-----v------+         +------v------+
        |   MySQL    |         |    Redis    |
        |   :3307    |         |   :6379     |
        +------------+         +-------------+
                                      |
                               +------v------+
                               |  ChromaDB   |
                               |   :8005     |
                               +-------------+
```

## 快速开始

### 环境要求

- Docker 20.10+
- Docker Compose 2.0+
- 阿里云百炼 API Key

### 1. 克隆项目

```bash
git clone https://github.com/xuechengxu-prog/smartnotes.git
cd smartnotes
```

### 2. 配置环境变量

创建 `.env` 文件：

```env
# MySQL
MYSQL_ROOT_PASSWORD=your_root_password
MYSQL_DATABASE=smartnotes
MYSQL_USER=smartnotes
MYSQL_PASSWORD=your_password

# LLM (阿里云百炼)
DASHSCOPE_API_KEY=your_dashscope_api_key
OPENAI_API_KEY=your_dashscope_api_key
LLM_MODEL=qwen3.7-plus
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

# JWT
JWT_SECRET=your-secret-key-change-in-production
```

### 3. 启动服务

```bash
docker-compose up -d
```

服务启动后访问：
- 前端页面: http://localhost
- 网关 API: http://localhost:8000
- API 文档: http://localhost:8000/docs

### 4. 服务端口说明

| 服务 | 端口 | 说明 |
|------|------|------|
| Frontend | 80 | Vue 前端页面 |
| Gateway | 8000 | 统一网关 API |
| Agent Note | 8001 | 笔记整理服务 |
| Agent Plan | 8002 | 复习计划服务 |
| Agent QA | 8003 | 问答服务 |
| MySQL | 3307 | 数据库 |
| Redis | 6379 | 缓存/会话 |
| ChromaDB | 8005 | 向量数据库 |

## 项目结构

```
smartnotes/
├── backend/                  # 后端服务
│   ├── agent_note/           # 笔记整理 Agent
│   ├── agent_plan/           # 复习计划 Agent
│   ├── agent_qa/             # 问答 Agent (ReAct)
│   ├── chains/               # LangChain 链定义
│   ├── common/               # 公共模块 (DB, Redis, JWT, Chroma)
│   ├── config/               # 配置管理
│   ├── gateway/              # 统一网关
│   ├── rag/                  # RAG 增强模块
│   │   ├── enhanced_rag.py   # 查询改写/数据清洗/智能切片/混合检索
│   │   ├── document_loader.py # 文档加载与预处理
│   │   ├── retriever.py      # RAG 检索器
│   │   └── knowledge_api.py   # 知识库 API
│   ├── services/             # 业务服务层
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/                 # 前端应用
│   ├── src/
│   │   ├── api/              # API 接口
│   │   ├── components/       # 公共组件
│   │   ├── router/           # 路由配置
│   │   ├── stores/           # Pinia 状态管理
│   │   ├── views/            # 页面视图
│   │   ├── App.vue
│   │   └── main.js
│   ├── Dockerfile
│   └── package.json
├── docker-compose.yml        # Docker 编排配置
├── init.sql                  # 数据库初始化
└── .env                      # 环境变量 (需自行创建)
```

## API 概览

### 认证接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/register` | 用户注册 |
| POST | `/api/auth/login` | 用户登录 |
| GET | `/api/auth/me` | 获取当前用户 |

### 笔记整理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/note/organize` | 整理笔记（流式） |

### 复习计划

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/plan/generate` | 生成复习计划（流式） |
| POST | `/api/plan/schedule` | 获取艾宾浩斯复习时间表 |

### 智能问答

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/qa/ask` | 问答（非流式） |
| POST | `/api/qa/ask/stream` | 问答（流式） |
| GET | `/api/qa/sessions` | 会话列表 |
| GET | `/api/qa/sessions/{id}/history` | 会话历史 |

### 知识库

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/knowledge/add/text` | 添加文本 |
| POST | `/api/knowledge/add/file` | 上传文件 |
| GET | `/api/knowledge/search` | 搜索知识库 |
| DELETE | `/api/knowledge/{id}` | 删除条目 |

## 核心设计

### ReAct Agent 架构

问答 Agent 采用 ReAct (Reasoning + Acting) 架构：

1. **Thought** - 分析用户问题，决定下一步行动
2. **Action** - 调用工具（知识库检索、计算等）
3. **Observation** - 获取工具执行结果
4. **Answer** - 综合信息生成最终回答

支持工具：
- `knowledge_search` - 检索用户知识库
- `calculator` - 数学计算

### 用户数据隔离

- 知识库按 `user_id` 隔离存储（collection: `user_{id}_default`）
- 会话历史按用户隔离存储于 Redis
- JWT Token 认证所有 API 请求

### 限流策略

基于 Redis 滑动窗口实现：
- 已登录用户：按用户 ID 限流
- 未登录用户：按 IP 限流

### 企业级 RAG 增强检索

问答 Agent 的知识库检索采用企业级 RAG 管道，覆盖从数据入库到检索生成的完整链路：

**数据入库管道：**
1. **数据清洗 (DataCleaner)** - 移除页眉页脚、过滤乱码/广告水印、连续段落去重
2. **智能切片 (SmartChunker)** - 基于中文标点的递归字符分块，自动携带元数据

**检索管道：**
1. **Query 改写 (QueryRewriter)** - Multi-Query 多角度改写 / HyDE 假设文档嵌入 / Step-Back 后退提示
2. **混合召回** - 语义向量检索 + BM25 关键词检索并行执行
3. **RRF 融合排序** - Reciprocal Rank Fusion (k=60) 合并多路召回结果
4. **MMR 多样性重排** - Maximal Marginal Relevance (lambda=0.55) 平衡相关性与多样性

## 开发指南

### 本地开发后端

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 启动网关
python -m uvicorn backend.gateway.main:app --reload --port 8000

# 启动各 Agent（分别开终端）
python -m uvicorn backend.agent_note.main:app --reload --port 8001
python -m uvicorn backend.agent_plan.main:app --reload --port 8002
python -m uvicorn backend.agent_qa.main:app --reload --port 8003
```

### 本地开发前端

```bash
cd frontend
npm install
npm run dev
```

## 许可证

MIT License
