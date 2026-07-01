# SmartNotes 智能学习助手 - 项目完整拆解文档（优化版）

> 本文档以"面试官视角"深度拆解 SmartNotes 项目，覆盖从用户请求到响应的完整链路，每个环节均标注对应源码位置。文档已同步更新至最新优化版本（v2.1.0）。

---

## 一、项目概述

### 1.1 项目定位

SmartNotes 是一款面向大学生的智能学习助手，基于 **FastAPI + Vue3 + LangChain + RAG** 技术栈构建，提供四大核心功能：

- **笔记整理**：将原始笔记自动整理为结构化 Markdown
- **复习计划**：基于艾宾浩斯遗忘曲线生成个性化复习计划
- **智能问答**：基于知识库 RAG 检索的 AI 问答
- **知识库管理**：支持文本/文件上传，语义搜索，按用户隔离

### 1.2 技术架构总览

```
+------------------------------------------------------------------+
|                        前端层 (Vue3)                              |
|  +----------+ +----------+ +----------+ +----------+             |
|  | 笔记整理  | | 复习计划  | | 智能问答  | | 知识库   |             |
|  +-----+----+ +-----+----+ +-----+----+ +-----+----+             |
|        |            |            |            |                  |
|        +------------+------------+------------+                  |
|                         marked + DOMPurify                       |
|                         Axios / Fetch                            |
+------------------------------------------------------------------+
                              |
                              v
+------------------------------------------------------------------+
|                      网关层 (Gateway)                             |
|  JWT 认证 | Redis 滑动窗口限流 | 路由转发 | 流式透传              |
|  Port: 8000                                                      |
+------------------------------------------------------------------+
                              |
          +-------------------+-------------------+
          |                   |                   |
          v                   v                   v
+-----------------+ +-----------------+ +-----------------+
|  笔记整理 Agent  | |  复习计划 Agent  | |   问答 Agent    |
|    Port: 8001   | |    Port: 8002   | |    Port: 8003   |
|  chains/note    | |  chains/plan    | |  chains/qa + RAG|
|                 | |                 | |  + 知识库管理    |
+-----------------+ +-----------------+ +-----------------+
                              |
          +-------------------+-------------------+
          |                   |                   |
          v                   v                   v
+-----------------+ +-----------------+ +-----------------+
|   MySQL 8.0     | |   Redis 6.2     | |   ChromaDB      |
|   用户/知识库    | |  限流/缓存/Session| |  向量数据库      |
|   Port: 3307    | |   Port: 6379    | |   Port: 8005    |
|  (aiomysql)     | |  (滑动窗口ZSET)  | |  (用户隔离)      |
+-----------------+ +-----------------+ +-----------------+
                              |
                              v
+------------------------------------------------------------------+
|                    大模型层 (百炼 qwen3.7-plus)                    |
|              https://dashscope.aliyuncs.com                      |
+------------------------------------------------------------------+
```

### 1.3 项目目录结构

```
smartnotes/
├── backend/                          # 后端服务
│   ├── gateway/                      # 统一网关
│   │   └── main.py                   # 网关入口：JWT/限流/路由转发/流式代理
│   ├── agent_note/                   # 笔记整理 Agent
│   │   └── main.py                   # 笔记服务入口（流式/非流式）
│   ├── agent_plan/                   # 复习计划 Agent
│   │   └── main.py                   # 计划服务入口（流式/非流式）
│   ├── agent_qa/                     # 问答 Agent（含知识库）
│   │   └── main.py                   # 问答服务入口（RAG/缓存/用户隔离）
│   ├── chains/                       # LangChain 链定义
│   │   ├── note_chain.py             # 笔记整理链
│   │   ├── plan_chain.py             # 复习计划链
│   │   └── qa_chain.py               # 问答链（RAG Prompt）
│   ├── common/                       # 公共模块
│   │   ├── ai_client.py              # AI 客户端兼容层
│   │   ├── chroma_client.py          # ChromaDB HttpClient 封装
│   │   ├── database.py               # MySQL + SQLAlchemy 异步连接池
│   │   ├── jwt_auth.py               # JWT Token 创建/验证/解码
│   │   └── redis_client.py           # Redis 限流/缓存/Session 封装
│   ├── config/
│   │   └── settings.py               # 全局配置（环境变量集中管理）
│   ├── rag/                          # RAG 模块
│   │   ├── document_loader.py        # 文档加载
│   │   ├── retriever.py              # 检索器
│   │   └── knowledge_api.py          # 知识库 API
│   ├── services/
│   │   └── llm_service.py            # LLM 服务封装（单例/懒加载）
│   ├── requirements.txt              # Python 依赖
│   └── Dockerfile                    # 后端镜像
├── frontend/                         # 前端应用
│   ├── src/
│   │   ├── api/                      # API 接口封装
│   │   │   ├── auth.js               # 认证接口
│   │   │   ├── knowledge.js          # 知识库接口
│   │   │   ├── note.js               # 笔记接口
│   │   │   ├── plan.js               # 计划接口
│   │   │   ├── qa.js                 # 问答接口
│   │   │   └── request.js            # Axios 请求封装（拦截器）
│   │   ├── components/               # 公共组件
│   │   │   ├── Header.vue            # 顶部导航
│   │   │   ├── Sidebar.vue           # 侧边栏
│   │   │   └── NoteCard.vue          # 笔记卡片
│   │   ├── stores/                   # Pinia 状态管理
│   │   │   ├── auth.js               # 认证状态（localStorage 同步）
│   │   │   └── cache.js              # 缓存状态
│   │   ├── views/                    # 页面视图
│   │   │   ├── Login.vue             # 登录页
│   │   │   ├── Register.vue          # 注册页
│   │   │   ├── Layout.vue            # 布局页
│   │   │   ├── Note.vue              # 笔记整理页（Markdown 实时渲染）
│   │   │   ├── Plan.vue              # 复习计划页（流式输出）
│   │   │   ├── QA.vue                # 智能问答页（思考中动画/打字机光标）
│   │   │   └── Knowledge.vue         # 知识库页（上传/搜索）
│   │   ├── router/
│   │   │   └── index.js              # Vue Router（路由守卫）
│   │   ├── main.js                   # 前端入口
│   │   └── websocket.js              # WebSocket 封装
│   ├── package.json                  # Node 依赖
│   ├── vite.config.js                # Vite 配置（代理/别名）
│   └── Dockerfile                    # 前端镜像（Nginx）
├── docker-compose.yml                # Docker Compose 编排
├── .env                              # 环境变量
└── SmartNotes项目完整拆解文档.md
```

---

## 二、核心链路拆解

### 链路 1：用户注册/登录链路

#### 2.1.1 链路流程图

```
用户输入账号密码
       |
       v
+--------------+     +--------------+     +--------------+
|  前端页面     |---->|  Axios 请求   |---->|  Gateway     |
| Login.vue    |     | request.js   |     | /auth/login  |
+--------------+     +--------------+     +------+-------+
                                                  |
                       +--------------------------+
                       v
              +----------------+
              |  JWTAuth 验证   |
              |  bcrypt 加密    |
              |  生成 Token    |
              +--------+-------+
                       |
          +------------+------------+
          |            |            |
          v            v            v
     +--------+  +--------+  +--------+
     | MySQL  |  | Redis  |  | 前端存储|
     | users  |  | Session|  |localStorage
     +--------+  +--------+  +--------+
```

#### 2.1.2 前端实现

**文件：`frontend/src/views/Login.vue`**

```vue
<template>
  <div class="auth-page">
    <div class="auth-card">
      <div class="auth-header">
        <h1>SmartNotes</h1>
        <p class="subtitle">智能学习助手</p>
      </div>
      <el-form :model="form" :rules="rules" ref="formRef" class="auth-form">
        <el-form-item prop="username">
          <el-input v-model="form.username" placeholder="用户名" :prefix-icon="User" />
        </el-form-item>
        <el-form-item prop="password">
          <el-input v-model="form.password" type="password" placeholder="密码" :prefix-icon="Lock" @keyup.enter="handleLogin" />
        </el-form-item>
        <el-button type="primary" size="large" class="auth-btn" :loading="loading" @click="handleLogin">
          登录
        </el-button>
      </el-form>
      <div class="auth-footer">
        <span>还没有账号？</span>
        <router-link to="/register" class="link">立即注册</router-link>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, Lock, Document } from '@element-plus/icons-vue'
import { login } from '@/api/auth.js'
import { useAuthStore } from '@/stores/auth.js'

const router = useRouter()
const authStore = useAuthStore()
const formRef = ref()
const loading = ref(false)

const form = reactive({ username: '', password: '' })
const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }]
}

const handleLogin = async () => {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  try {
    const res = await login(form)           // 调用 auth.js 接口
    authStore.setAuth(res.token, form.username)  // Pinia 存储认证状态
    ElMessage.success('登录成功')
    router.push('/')                        // 跳转到首页
  } catch (e) {
    // 错误由 request.js 拦截器统一处理
  } finally {
    loading.value = false
  }
}
</script>
```

**文件：`frontend/src/api/auth.js`**

```javascript
import request from './request.js'

export const login = (data) => request.post('/auth/login', data)
export const register = (data) => request.post('/auth/register', data)
```

**文件：`frontend/src/api/request.js` - Axios 拦截器**

```javascript
import axios from 'axios'
import { ElMessage } from 'element-plus'

const request = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' }
})

// 请求拦截器：自动附加 JWT Token
request.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// 响应拦截器：统一错误处理
request.interceptors.response.use(
  (response) => response.data,
  (error) => {
    if (error.response) {
      const status = error.response.status
      const detail = error.response.data?.detail || '请求失败'
      const url = error.config?.url || ''

      // 登录接口的 401：用户名或密码错误
      if (status === 401 && url.includes('/auth/login')) {
        ElMessage.error('用户名或密码错误')
      }
      // 注册接口的 422：参数验证失败
      else if (status === 422 && url.includes('/auth/register')) {
        ElMessage.error(detail)
      }
      // 其他接口的 401：token 过期
      else if (status === 401) {
        ElMessage.error('登录已过期，请重新登录')
        localStorage.removeItem('token')
        localStorage.removeItem('username')
        window.location.href = '/login'
      } else if (status === 422) {
        ElMessage.error(detail)
      } else {
        ElMessage.error(detail)
      }
    } else {
      ElMessage.error('网络错误，请检查连接')
    }
    return Promise.reject(error)
  }
)

export default request
```

**文件：`frontend/src/stores/auth.js` - Pinia 认证状态**

```javascript
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token') || '')
  const username = ref(localStorage.getItem('username') || '')

  const isLoggedIn = computed(() => !!token.value)

  const setAuth = (newToken, newUsername) => {
    token.value = newToken
    username.value = newUsername
    localStorage.setItem('token', newToken)
    localStorage.setItem('username', newUsername)
  }

  const clearAuth = () => {
    token.value = ''
    username.value = ''
    localStorage.removeItem('token')
    localStorage.removeItem('username')
  }

  const logout = () => {
    clearAuth()
    window.location.href = '/login'
  }

  return { token, username, isLoggedIn, setAuth, clearAuth, logout }
})
```

**文件：`frontend/src/router/index.js` - 路由守卫**

```javascript
import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth.js'

const routes = [
  { path: '/login', name: 'Login', component: () => import('@/views/Login.vue'), meta: { public: true } },
  { path: '/register', name: 'Register', component: () => import('@/views/Register.vue'), meta: { public: true } },
  {
    path: '/', component: () => import('@/views/Layout.vue'), redirect: '/note',
    children: [
      { path: 'note', name: 'Note', component: () => import('@/views/Note.vue') },
      { path: 'plan', name: 'Plan', component: () => import('@/views/Plan.vue') },
      { path: 'qa', name: 'QA', component: () => import('@/views/QA.vue') },
      { path: 'knowledge', name: 'Knowledge', component: () => import('@/views/Knowledge.vue') }
    ]
  }
]

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach((to, from, next) => {
  const authStore = useAuthStore()
  if (!to.meta.public && !authStore.isLoggedIn) {
    next('/login')
  } else {
    next()
  }
})

export default router
```

#### 2.1.3 后端实现

**文件：`backend/gateway/main.py`**

```python
import bcrypt
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from backend.common.jwt_auth import JWTAuth
from backend.common.database import get_db_session, User

# Pydantic 请求模型
class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    email: str = Field("", description="邮箱")
    password: str = Field(..., min_length=6)

class LoginRequest(BaseModel):
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")

class AuthResponse(BaseModel):
    token: str = Field(..., description="JWT Token")
    user_id: int = Field(..., description="用户 ID")
    username: str = Field(..., description="用户名")

def _hash_password(password: str) -> str:
    """使用 bcrypt 加密密码"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def _verify_password(password: str, hashed: str) -> bool:
    """验证密码"""
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))

# 注册接口
@app.post("/api/auth/register", response_model=AuthResponse)
async def register(request: RegisterRequest):
    session = await get_db_session()
    try:
        # 检查用户名是否已存在
        result = await session.execute(select(User).where(User.username == request.username))
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="用户名已存在")

        # 检查邮箱是否已存在
        if request.email:
            result = await session.execute(select(User).where(User.email == request.email))
            if result.scalar_one_or_none():
                raise HTTPException(status_code=400, detail="邮箱已存在")

        # 创建用户
        password_hash = _hash_password(request.password)
        user = User(username=request.username, email=request.email or None, password_hash=password_hash)
        session.add(user)
        await session.commit()
        await session.refresh(user)

        # 生成 JWT Token
        token = JWTAuth.create_token(user_id=user.id, username=user.username)
        return AuthResponse(token=token, user_id=user.id, username=user.username)
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"注册失败: {str(e)}")
    finally:
        await session.close()

# 登录接口
@app.post("/api/auth/login", response_model=AuthResponse)
async def login(request: LoginRequest):
    session = await get_db_session()
    try:
        # 1. 查询 MySQL 用户表
        result = await session.execute(select(User).where(User.username == request.username))
        user = result.scalar_one_or_none()

        # 2. bcrypt 验证密码
        if not user or not _verify_password(request.password, user.password_hash):
            raise HTTPException(status_code=401, detail="用户名或密码错误")

        # 3. 生成 JWT Token
        token = JWTAuth.create_token(user_id=user.id, username=user.username)
        return AuthResponse(token=token, user_id=user.id, username=user.username)
    finally:
        await session.close()

# 获取当前用户信息
@app.get("/api/auth/me")
async def get_me(request: Request):
    user = await JWTAuth.get_current_user(request)
    return { "user_id": user["user_id"], "username": user["username"] }
```

**文件：`backend/common/jwt_auth.py`**

```python
import jwt
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, Request
from fastapi.security import HTTPBearer

from backend.config.settings import settings

security = HTTPBearer(auto_error=False)

class JWTAuth:
    @staticmethod
    def create_token(user_id: int, username: str, extra_claims=None) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "sub": str(user_id),                                    # 用户ID
            "username": username,
            "iat": now,                                             # 签发时间
            "exp": now + timedelta(hours=settings.JWT_EXPIRE_HOURS), # 过期时间
            "type": "access",
        }
        if extra_claims:
            payload.update(extra_claims)
        token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
        return token

    @staticmethod
    def decode_token(token: str) -> dict:
        try:
            payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token 已过期")
        except jwt.InvalidTokenError as e:
            raise HTTPException(status_code=401, detail="无效的 Token")

    @staticmethod
    def get_user_id_from_token(token: str) -> int:
        payload = JWTAuth.decode_token(token)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Token 中未找到用户 ID")
        return int(user_id)

    @staticmethod
    async def get_current_user(request: Request, credentials=None) -> dict:
        """获取当前用户（优先从 Header 获取，其次从 Cookie 获取）"""
        token = None
        if credentials:
            token = credentials.credentials
        else:
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header[7:]
        if not token:
            token = request.cookies.get("access_token")
        if not token:
            raise HTTPException(status_code=401, detail="未提供认证信息")

        payload = JWTAuth.decode_token(token)
        return { "user_id": int(payload.get("sub", 0)), "username": payload.get("username", "") }
```

**文件：`backend/common/database.py`**

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Index
from sqlalchemy.sql import func

from backend.config.settings import settings

Base = declarative_base()

class User(Base):
    """用户表"""
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    email = Column(String(128), unique=True, nullable=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class KnowledgeItem(Base):
    """知识库条目表 - 存储 ChromaDB 元数据镜像"""
    __tablename__ = "knowledge_items"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    collection_name = Column(String(128), nullable=False, default="default")
    content = Column(Text, nullable=False)
    filename = Column(String(512), nullable=True)
    chroma_id = Column(String(128), nullable=True, comment="ChromaDB 中的文档 ID")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

# 异步引擎（aiomysql）
async_engine = create_async_engine(
    settings.mysql_url,
    pool_size=settings.MYSQL_POOL_SIZE,           # 10
    max_overflow=settings.MYSQL_POOL_OVERFLOW,    # 20
    pool_timeout=settings.MYSQL_POOL_TIMEOUT,     # 30
    pool_recycle=3600,
    echo=False,
)

# 异步会话工厂
AsyncSessionLocal = async_sessionmaker(
    async_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)

async def init_database() -> None:
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def close_database() -> None:
    await async_engine.dispose()

async def get_db_session() -> AsyncSession:
    return AsyncSessionLocal()
```

---

### 链路 2：笔记整理链路（流式输出 + Markdown 实时渲染）

#### 2.2.1 链路流程图

```
用户粘贴笔记内容
       |
       v
+--------------+     +--------------+     +--------------+
|  Note.vue    |---->|  fetch POST   |---->|  Gateway     |
| 原始笔记输入  |     | /api/note/    |     | proxy_note() |
+--------------+     +--------------+     +------+-------+
                                                  |
                       +--------------------------+
                       v
              +----------------+
              | Agent Note     |
              | /organize/stream|
              +--------+-------+
                       |
              +--------+--------+
              |                 |
              v                 v
        +----------+    +----------+
        |note_chain|    | LLMService|
        | organize |    | qwen3.7  |
        | _stream()|    | 流式输出  |
        +----------+    +----------+
              |
              v
       +--------------+
       | marked +     |
       | DOMPurify    |
       | 实时渲染     |
       +--------------+
```

#### 2.2.2 前端实现

**文件：`frontend/src/views/Note.vue`**

```vue
<template>
  <div class="page-container">
    <div class="input-section">
      <el-input v-model="rawNote" type="textarea" :rows="8" placeholder="在此粘贴你的原始笔记内容..." class="dark-textarea" />
      <div class="actions">
        <el-button type="primary" size="large" :loading="loading" :disabled="!rawNote.trim()" @click="handleOrganize">
          <el-icon class="btn-icon"><MagicStick /></el-icon>智能整理
        </el-button>
        <el-button size="large" :disabled="!result" @click="copyResult">
          <el-icon class="btn-icon"><CopyDocument /></el-icon>复制结果
        </el-button>
      </div>
    </div>

    <div v-if="result || streaming" class="result-section">
      <div class="result-header">
        <el-icon size="18" color="#00f0ff"><DocumentChecked /></el-icon>
        <span>整理结果</span>
        <span v-if="streaming" class="typing-indicator">
          <span class="dot"></span><span class="dot"></span><span class="dot"></span>
        </span>
      </div>
      <!-- 关键：Markdown 实时渲染 -->
      <div class="result-content markdown-body" v-html="renderedMarkdown"></div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick, CopyDocument, DocumentChecked } from '@element-plus/icons-vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

// 配置 marked
marked.setOptions({ gfm: true, breaks: true, headerIds: false, mangle: false })

const rawNote = ref('')
const result = ref('')
const loading = ref(false)
const streaming = ref(false)

// 关键：实时渲染 Markdown（使用 computed + DOMPurify 防 XSS）
const renderedMarkdown = computed(() => {
  if (!result.value) return ''
  const html = marked.parse(result.value)
  return DOMPurify.sanitize(html)
})

const handleOrganize = async () => {
  if (!rawNote.value.trim()) return
  loading.value = true
  streaming.value = true
  result.value = ''

  try {
    const token = localStorage.getItem('token')
    const response = await fetch('/api/note/organize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify({ content: rawNote.value })
    })

    if (!response.ok) {
      if (response.status === 401) {
        ElMessage.error('登录已过期，请重新登录')
        localStorage.removeItem('token')
        window.location.href = '/login'
        return
      }
      throw new Error('请求失败')
    }

    // 流式读取
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      const chunk = decoder.decode(value, { stream: true })
      if (chunk && chunk.trim()) {
        result.value += chunk
      }
    }
  } catch (e) {
    ElMessage.error('整理失败: ' + e.message)
  } finally {
    loading.value = false
    streaming.value = false
  }
}

const copyResult = () => {
  navigator.clipboard.writeText(result.value)
  ElMessage.success('已复制到剪贴板')
}
</script>
```

#### 2.2.3 后端实现

**文件：`backend/gateway/main.py` - 路由转发**

```python
@app.post("/api/note/{path:path}")
async def proxy_note(request: Request, path: str):
    """转发到笔记整理 Agent（流式）"""
    user = await JWTAuth.get_current_user(request)
    body = await request.json()

    # 笔记整理使用 /organize/stream 端点
    stream_path = "/organize/stream"

    return await _proxy_stream_request(
        service_host=settings.AGENT_NOTE_HOST,    # agent_note
        service_port=settings.AGENT_NOTE_PORT,    # 8001
        path=stream_path,
        body=body,
        user_id=user["user_id"],
    )
```

**文件：`backend/agent_note/main.py`**

```python
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.chains.note_chain import note_chain
from backend.common.redis_client import redis_client
from backend.config.settings import settings

class NoteOrganizeRequest(BaseModel):
    content: str = Field(..., min_length=1, description="原始笔记内容")
    style: str = Field(None, description="整理风格要求")
    stream: bool = Field(False, description="是否流式输出")

@app.post("/organize/stream")
async def organize_note_stream(request: NoteOrganizeRequest):
    """整理笔记（流式输出）"""
    if not request.content.strip():
        raise HTTPException(status_code=400, detail="笔记内容不能为空")

    async def generate():
        try:
            async for chunk in note_chain.organize_stream(
                content=request.content,
                style=request.style,
            ):
                if chunk and chunk.strip():
                    yield chunk
        except Exception as e:
            yield f"\n[错误] 笔记整理失败: {str(e)}"

    return StreamingResponse(generate(), media_type="text/plain; charset=utf-8")
```

**文件：`backend/chains/note_chain.py`**

```python
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from backend.services.llm_service import llm_service

# 笔记整理系统提示词
NOTE_SYSTEM_PROMPT = """你是一位专业的学习笔记整理助手。你的任务是将用户提供的原始笔记内容整理为结构清晰、重点突出的学习笔记。

整理要求：
1. 提取核心概念和关键知识点
2. 使用层级标题组织内容（# 一级标题, ## 二级标题, ### 三级标题）
3. 对重要内容使用加粗标记
4. 将列表内容整理为有序或无序列表
5. 添加适当的总结和归纳
6. 保持内容的准确性和完整性
7. 使用 Markdown 格式输出

输出格式：
- 开头简要概述笔记主题
- 主体部分按知识点分层展开
- 结尾提供关键要点总结
"""

NOTE_HUMAN_TEMPLATE = """请帮我整理以下笔记内容：

原始笔记：
{content}

{style_hint}
"""

class NoteChain:
    def __init__(self):
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", NOTE_SYSTEM_PROMPT),
            ("human", NOTE_HUMAN_TEMPLATE),
        ])
        self.output_parser = StrOutputParser()
        # 构建链: prompt -> llm -> parser
        self.chain = self.prompt | llm_service.llm | self.output_parser

    async def organize_stream(self, content: str, style: str = None):
        style_hint = f"整理风格要求：{style}" if style else ""
        async for chunk in self.chain.astream({"content": content, "style_hint": style_hint}):
            yield chunk

note_chain = NoteChain()
```

**文件：`backend/services/llm_service.py`**

```python
from langchain_openai import ChatOpenAI
from backend.config.settings import settings

class LLMService:
    _instance = None
    _llm = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @property
    def llm(self) -> ChatOpenAI:
        if self._llm is None:
            self._llm = ChatOpenAI(
                model=settings.LLM_MODEL,              # "qwen3.7-plus"
                api_key=settings.DASHSCOPE_API_KEY,
                base_url=settings.LLM_BASE_URL,        # 百炼兼容端点
                temperature=settings.LLM_TEMPERATURE,  # 0.7
                max_tokens=settings.LLM_MAX_TOKENS,    # 4096
                timeout=settings.LLM_TIMEOUT,          # 60
                streaming=True,                         # 启用流式
            )
        return self._llm

llm_service = LLMService()
```

---

### 链路 3：复习计划链路（流式输出修复）

#### 2.3.1 链路流程图

```
用户输入科目、日期、时长
       |
       v
+--------------+     +--------------+     +--------------+
|  Plan.vue    |---->|  fetch POST   |---->|  Gateway     |
| 表单输入      |     | /api/plan/    |     | proxy_plan() |
+--------------+     +--------------+     +------+-------+
                                                  |
                       +--------------------------+
                       v
              +----------------+
              | Agent Plan     |
              | /generate/stream|
              +--------+-------+
                       |
              +--------+--------+
              |                 |
              v                 v
        +----------+    +----------+
        |plan_chain|    | LLMService|
        |generate  |    | qwen3.7  |
        |_plan()   |    | 流式输出  |
        +----------+    +----------+
              |
              v
       +--------------+
       | 移除 chunk.  |
       | trim() 过滤  |
       | 确保内容完整 |
       +--------------+
```

#### 2.3.2 前端实现

**文件：`frontend/src/views/Plan.vue`**

```vue
<template>
  <div class="page-container">
    <div class="form-section">
      <el-form :model="form" label-position="top" class="plan-form">
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="科目">
              <el-input v-model="form.subject" placeholder="例如：高等数学" size="large" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="每日学习时长（小时）">
              <el-input-number v-model="form.daily_hours" :min="0.5" :max="12" :step="0.5" size="large" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="开始日期">
              <el-date-picker v-model="form.start_date" type="date" placeholder="选择开始日期" size="large" style="width: 100%" value-format="YYYY-MM-DD" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="结束日期">
              <el-date-picker v-model="form.end_date" type="date" placeholder="选择结束日期" size="large" style="width: 100%" value-format="YYYY-MM-DD" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item>
          <el-button type="primary" size="large" :loading="loading" :disabled="!canSubmit" @click="handleGenerate">
            <el-icon class="btn-icon"><Calendar /></el-icon>生成复习计划
          </el-button>
        </el-form-item>
      </el-form>
    </div>

    <div v-if="result || streaming" class="result-section">
      <div class="result-header">
        <el-icon size="18" color="#00f0ff"><DocumentChecked /></el-icon>
        <span>复习计划</span>
        <span v-if="streaming" class="typing-indicator">
          <span class="dot"></span><span class="dot"></span><span class="dot"></span>
        </span>
      </div>
      <!-- Markdown 实时渲染 -->
      <div class="result-content markdown-body" v-html="renderedMarkdown"></div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Calendar, DocumentChecked } from '@element-plus/icons-vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

marked.setOptions({ gfm: true, breaks: true, headerIds: false, mangle: false })

const form = ref({ subject: '', start_date: '', end_date: '', daily_hours: 2 })
const loading = ref(false)
const streaming = ref(false)
const result = ref('')

const canSubmit = computed(() => {
  return form.value.subject && form.value.start_date && form.value.end_date && form.value.daily_hours > 0
})

const renderedMarkdown = computed(() => {
  if (!result.value) return ''
  const html = marked.parse(result.value)
  return DOMPurify.sanitize(html)
})

const handleGenerate = async () => {
  if (!canSubmit.value) return
  loading.value = true
  streaming.value = true
  result.value = ''

  try {
    const token = localStorage.getItem('token')
    const response = await fetch('/api/plan/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify({
        content: `科目：${form.value.subject}\n开始日期：${form.value.start_date}\n结束日期：${form.value.end_date}\n每日学习时长：${form.value.daily_hours}小时`,
        days: Math.ceil((new Date(form.value.end_date) - new Date(form.value.start_date)) / (1000 * 60 * 60 * 24)),
        sessions_per_day: Math.max(1, Math.round(form.value.daily_hours)),
        focus_areas: form.value.subject
      })
    })

    if (!response.ok) {
      if (response.status === 401) {
        ElMessage.error('登录已过期，请重新登录')
        localStorage.removeItem('token')
        window.location.href = '/login'
        return
      }
      throw new Error('请求失败')
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let receivedAny = false

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      const chunk = decoder.decode(value, { stream: true })
      // 关键修复：必须累加所有 chunk，包括空白，否则内容会丢失
      result.value += chunk
      if (chunk) receivedAny = true
    }

    // 如果完全没有收到内容，给出提示
    if (!receivedAny || !result.value.trim()) {
      result.value = '抱歉，未能生成复习计划，请重试。'
    }
  } catch (e) {
    ElMessage.error('生成失败: ' + e.message)
  } finally {
    loading.value = false
    streaming.value = false
  }
}
</script>
```

#### 2.3.3 后端实现

**文件：`backend/agent_plan/main.py`**

```python
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.chains.plan_chain import plan_chain
from backend.common.redis_client import redis_client
from backend.config.settings import settings

class PlanGenerateRequest(BaseModel):
    content: str = Field(..., min_length=1, description="笔记内容")
    days: int = Field(30, ge=1, le=365, description="计划总天数")
    sessions_per_day: int = Field(2, ge=1, le=10, description="每天复习次数")
    focus_areas: str = Field(None, description="重点复习领域")
    stream: bool = Field(False, description="是否流式输出")

@app.post("/generate/stream")
async def generate_plan_stream(request: PlanGenerateRequest):
    """生成复习计划（流式输出）"""
    if not request.content.strip():
        raise HTTPException(status_code=400, detail="笔记内容不能为空")

    async def generate():
        try:
            async for chunk in plan_chain.generate_plan_stream(
                content=request.content,
                days=request.days,
                sessions_per_day=request.sessions_per_day,
                focus_areas=request.focus_areas,
            ):
                if chunk and chunk.strip():
                    yield chunk
        except Exception as e:
            yield f"\n[错误] 计划生成失败: {str(e)}"

    return StreamingResponse(generate(), media_type="text/plain; charset=utf-8")

@app.post("/schedule")
async def get_schedule(request: PlanGenerateRequest):
    """获取基于艾宾浩斯遗忘曲线的复习时间表"""
    schedule = plan_chain.get_review_schedule(days=request.days)
    return { "schedule": schedule }
```

**文件：`backend/chains/plan_chain.py`**

```python
from datetime import datetime, timedelta
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from backend.services.llm_service import llm_service

PLAN_SYSTEM_PROMPT = """你是一位专业的学习规划师。你的任务是根据用户的学习笔记内容，制定科学、高效的复习计划。

复习计划要求：
1. 基于艾宾浩斯遗忘曲线设计复习间隔
2. 将复习内容合理分配到不同时间段
3. 每次复习明确标注重点内容和复习目标
4. 提供具体的复习方法和建议
5. 计划应具有可操作性，时间分配合理
6. 使用 Markdown 格式输出

输出格式：
- 总体复习策略概述
- 按时间线排列的复习计划表
- 每次复习的具体内容和方法
- 复习效果自测建议
"""

PLAN_HUMAN_TEMPLATE = """请根据以下笔记内容帮我制定复习计划：

笔记内容：
{content}

{preferences}
"""

class PlanChain:
    def __init__(self):
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", PLAN_SYSTEM_PROMPT),
            ("human", PLAN_HUMAN_TEMPLATE),
        ])
        self.output_parser = StrOutputParser()
        self.chain = self.prompt | llm_service.llm | self.output_parser

    async def generate_plan_stream(self, content, days=30, sessions_per_day=2, focus_areas=None):
        preferences = f"""复习偏好：
- 计划总时长：{days} 天
- 每天复习次数：{sessions_per_day} 次
{f'- 重点复习领域：{focus_areas}' if focus_areas else ''}"""

        async for chunk in self.chain.astream({"content": content, "preferences": preferences}):
            yield chunk

    def get_review_schedule(self, start_date=None, days=30):
        """生成基于艾宾浩斯遗忘曲线的复习时间表"""
        if start_date is None:
            start_date = datetime.now()

        # 艾宾浩斯复习间隔（天）：1, 2, 4, 7, 15, 30
        intervals = [1, 2, 4, 7, 15, 30]
        schedule = []

        for day in range(days):
            current_date = start_date + timedelta(days=day)
            reviews = []
            for interval in intervals:
                if day % interval == 0 and day > 0:
                    reviews.append(f"第 {interval} 天间隔复习")
            if reviews:
                schedule.append({
                    "date": current_date.strftime("%Y-%m-%d"),
                    "day": day + 1,
                    "reviews": reviews,
                })
        return schedule

plan_chain = PlanChain()
```

---

### 链路 4：智能问答链路（RAG 检索增强 + 用户隔离 + 模型版本缓存）

#### 2.4.1 链路流程图

```
用户输入问题
       |
       v
+--------------+     +--------------+     +--------------+
|   QA.vue     |---->|  fetch POST   |---->|  Gateway     |
| 问题输入      |     | /api/qa/ask   |     | proxy_qa()   |
+--------------+     +--------------+     +------+-------+
                                                  |
                       +--------------------------+
                       v
              +----------------+
              |   Agent QA     |
              |  /ask/stream   |
              +--------+-------+
                       |
         +-------------+-------------+
         |             |             |
         v             v             v
    +--------+   +--------+   +--------+
    |ChromaDB|   | Redis  |   |qa_chain|
    |search()|   | cache  |   |answer  |
    |用户隔离 |   |模型版本|   |_stream |
    +--------+   +--------+   +----+---+
         |                        |
         v                        v
    +----------------+    +----------------+
    | user_{id}_     |    | LLMService     |
    | default        |    | RAG Prompt     |
    | 向量检索        |    | 流式输出        |
    +----------------+    +----------------+
```

#### 2.4.2 前端实现

**文件：`frontend/src/views/QA.vue`**

```vue
<template>
  <div class="page-container">
    <div class="chat-container">
      <div class="messages" ref="messagesRef">
        <div v-for="(msg, index) in messages" :key="index" :class="['message', msg.role]">
          <div class="message-avatar">
            <el-icon size="20" :color="msg.role === 'user' ? '#00f0ff' : '#a855f7'">
              <component :is="msg.role === 'user' ? User : ChatDotRound" />
            </el-icon>
          </div>
          <div class="message-bubble">
            <!-- 关键：思考中动画 -->
            <div v-if="msg.role === 'assistant' && msg.thinking" class="thinking-indicator">
              <span class="dot"></span><span class="dot"></span><span class="dot"></span>
            </div>
            <!-- Markdown 渲染 -->
            <div v-else class="markdown-body" v-html="renderMarkdown(msg.content)"></div>
            <!-- 关键：打字机光标效果 -->
            <span v-if="msg.role === 'assistant' && msg.streaming && !msg.thinking" class="typing-cursor">|</span>
          </div>
        </div>
        <div v-if="messages.length === 0" class="empty-state">
          <el-icon size="48" color="rgba(0, 240, 255, 0.3)"><ChatDotRound /></el-icon>
          <p>开始你的智能问答之旅</p>
          <span class="hint">输入问题，AI 将基于知识库为你解答</span>
        </div>
      </div>

      <div class="input-area">
        <el-input v-model="question" type="textarea" :rows="2" placeholder="输入你的问题..." class="chat-input" @keyup.enter.ctrl="handleAsk" />
        <el-button type="primary" class="send-btn" :loading="loading" :disabled="!question.trim()" @click="handleAsk">
          <el-icon size="18"><Promotion /></el-icon>
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { ChatDotRound, User, Promotion } from '@element-plus/icons-vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

marked.setOptions({ gfm: true, breaks: true, headerIds: false, mangle: false })

const question = ref('')
const messages = ref([])
const loading = ref(false)
const messagesRef = ref()

const renderMarkdown = (content) => {
  if (!content) return ''
  const html = marked.parse(content)
  return DOMPurify.sanitize(html)
}

const scrollToBottom = () => {
  if (messagesRef.value) {
    messagesRef.value.scrollTop = messagesRef.value.scrollHeight
  }
}

const handleAsk = async () => {
  if (!question.value.trim() || loading.value) return

  const userQuestion = question.value.trim()
  messages.value.push({ role: 'user', content: userQuestion })
  question.value = ''
  loading.value = true
  await nextTick()
  scrollToBottom()

  // 关键：先显示"思考中"状态
  const assistantIndex = messages.value.length
  messages.value.push({ role: 'assistant', content: '', streaming: true, thinking: true })
  await nextTick()
  scrollToBottom()

  try {
    const token = localStorage.getItem('token')
    const response = await fetch('/api/qa/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify({ question: userQuestion })
    })

    if (!response.ok) {
      if (response.status === 401) {
        ElMessage.error('登录已过期，请重新登录')
        localStorage.removeItem('token')
        window.location.href = '/login'
        return
      }
      throw new Error('请求失败')
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let firstContent = true
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      const chunk = decoder.decode(value, { stream: true })
      buffer += chunk

      // 每收到数据就更新 UI（不过滤空内容，让 Vue 自己处理）
      if (firstContent && buffer.trim()) {
        messages.value[assistantIndex].thinking = false
        firstContent = false
      }
      messages.value[assistantIndex].content = buffer
      scrollToBottom()
    }

    if (firstContent) {
      messages.value[assistantIndex].thinking = false
      messages.value[assistantIndex].content = '抱歉，没有收到回复内容。'
    }
  } catch (e) {
    messages.value[assistantIndex].thinking = false
    messages.value[assistantIndex].content = '抱歉，回答时出错了: ' + e.message
  } finally {
    messages.value[assistantIndex].streaming = false
    loading.value = false
    await nextTick()
    scrollToBottom()
  }
}
</script>
```

#### 2.4.3 后端实现

**文件：`backend/agent_qa/main.py`**

```python
import hashlib
import uuid
from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.chains.qa_chain import qa_chain
from backend.common.redis_client import redis_client
from backend.common.chroma_client import chroma_client
from backend.common.database import init_database, close_database, get_db_session, KnowledgeItem
from backend.config.settings import settings

class QARequest(BaseModel):
    question: str = Field(..., min_length=1, description="用户问题")
    context: str = Field(None, description="知识库上下文（可选，不传则自动检索）")
    stream: bool = Field(False, description="是否流式输出")
    use_cache: bool = Field(True, description="是否使用缓存")

class QAResponse(BaseModel):
    answer: str = Field(..., description="回答内容")
    cache_hit: bool = Field(False, description="是否命中缓存")

# ============================================================
# 关键优化 1：知识库按用户隔离
# ============================================================
def _get_user_collection(user_id: int, collection_name: str = None) -> str:
    """
    获取用户隔离的 collection 名称
    格式：user_{id}_{name} 或 user_{id}_default
    """
    if collection_name:
        return f"user_{user_id}_{collection_name}"
    return f"user_{user_id}_default"

# ============================================================
# 关键优化 2：LLM 缓存 key 包含模型版本号
# ============================================================
def _generate_cache_key(question: str, context: str = None) -> str:
    """生成缓存 key（包含模型版本，避免模型升级后缓存失效）"""
    key_content = f"qa:{settings.LLM_MODEL}:{question}:{context or ''}"
    return hashlib.md5(key_content.encode()).hexdigest()

def _build_context_from_search_results(results: dict) -> str:
    """将 ChromaDB 搜索结果拼接为上下文字符串"""
    if not results or not results.get("documents"):
        return ""
    documents = results["documents"]
    metadatas = results.get("metadatas", [[] for _ in documents])
    parts = []
    for i, doc_list in enumerate(documents):
        for j, doc in enumerate(doc_list):
            meta = metadatas[i][j] if i < len(metadatas) and j < len(metadatas[i]) else {}
            source = meta.get("filename", "未知来源")
            parts.append(f"[文档 {j+1} - {source}]\n{doc}")
    return "\n\n---\n\n".join(parts) if parts else ""

async def _save_qa_to_chromadb(user_id: int, question: str, answer: str):
    """将 QA 问答结果存入 ChromaDB 向量数据库（使用用户隔离 collection）"""
    try:
        qa_text = f"问题：{question}\n\n回答：{answer}"
        item_id = f"qa_{user_id}_{uuid.uuid4().hex[:8]}"
        collection = _get_user_collection(user_id)
        chroma_client.add_texts(
            collection_name=collection,
            texts=[qa_text],
            metadatas=[{"user_id": str(user_id), "type": "qa_record", "question": question[:200]}],
            ids=[item_id],
        )
    except Exception as e:
        logger.error(f"Failed to save QA to ChromaDB: {e}")

# 问答（非流式，带缓存和知识库检索）
@app.post("/ask", response_model=QAResponse)
async def ask_question(request: QARequest, x_user_id: int = Header(...)):
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="问题不能为空")

    cache_key = None
    cache_hit = False
    answer = None

    # 如果未手动传入 context，自动从 ChromaDB 检索（用户隔离 collection）
    context = request.context
    if not context:
        try:
            user_collection = _get_user_collection(x_user_id)
            search_results = chroma_client.search(
                collection_name=user_collection,
                query_text=request.question,
                n_results=5,
            )
            context = _build_context_from_search_results(search_results)
        except Exception as e:
            context = ""

    # 尝试从 Redis 缓存获取（包含模型版本）
    if request.use_cache:
        cache_key = _generate_cache_key(request.question, context)
        cached = await redis_client.cache_get(cache_key)
        if cached:
            answer = cached
            cache_hit = True

    # 缓存未命中，调用 LLM
    if answer is None:
        full_answer = ""
        async for chunk in qa_chain.answer_stream(question=request.question, context=context or ""):
            if chunk and chunk.strip():
                full_answer += chunk
        answer = full_answer

        # 写入 Redis 缓存
        if request.use_cache and cache_key:
            await redis_client.cache_set(cache_key, answer, ttl=settings.CACHE_TTL)

    # 保存到 ChromaDB（用户隔离 collection）
    await _save_qa_to_chromadb(x_user_id, request.question, answer)

    return QAResponse(answer=answer, cache_hit=cache_hit)

# 问答（流式输出）
@app.post("/ask/stream")
async def ask_question_stream(request: QARequest, x_user_id: int = Header(...)):
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="问题不能为空")

    # 自动检索 ChromaDB 知识库（用户隔离）
    context = request.context
    if not context:
        try:
            user_collection = _get_user_collection(x_user_id)
            search_results = chroma_client.search(
                collection_name=user_collection,
                query_text=request.question,
                n_results=5,
            )
            context = _build_context_from_search_results(search_results)
        except Exception as e:
            context = ""

    answer_parts = []

    async def generate():
        async for chunk in qa_chain.answer_stream(question=request.question, context=context or ""):
            if chunk and chunk.strip():
                answer_parts.append(chunk)
                yield chunk

    async def stream_with_save():
        async for chunk in generate():
            yield chunk
        # 流式结束后保存完整回答到 ChromaDB
        full_answer = "".join(answer_parts)
        if full_answer:
            await _save_qa_to_chromadb(x_user_id, request.question, full_answer)

    return StreamingResponse(stream_with_save(), media_type="text/plain; charset=utf-8")
```

**文件：`backend/chains/qa_chain.py`**

```python
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from backend.services.llm_service import LLMService

class QAChain:
    """问答 LangChain 链，支持 RAG"""

    def __init__(self):
        self.llm = LLMService().get_llm()
        # RAG 检索提示词模板
        self.rag_prompt = ChatPromptTemplate.from_messages([
            ("system", """你是一个智能学习助手。请根据以下检索到的知识库内容来回答用户的问题。
如果知识库中没有相关内容，请根据你的知识回答，但请注明"此回答未基于知识库内容"。

检索到的相关文档：
{context}

请用清晰、结构化的方式回答问题。"""),
            ("user", "{question}")
        ])
        # 普通问答提示词（无知识库内容时）
        self.normal_prompt = ChatPromptTemplate.from_messages([
            ("system", "你是一个智能学习助手。请用清晰、结构化的方式回答学生的问题。"),
            ("user", "{question}")
        ])

    async def answer_stream(self, question: str, context: str = ""):
        """流式回答问题，支持 RAG"""
        if context:
            chain = self.rag_prompt | self.llm | StrOutputParser()
            async for chunk in chain.astream({"question": question, "context": context}):
                yield chunk
        else:
            chain = self.normal_prompt | self.llm | StrOutputParser()
            async for chunk in chain.astream({"question": question}):
                yield chunk

qa_chain = QAChain()
```

---

### 链路 5：知识库管理链路（批量写入 + 删除同步清理）

#### 2.5.1 链路流程图

```
用户上传文本/文件
       |
       v
+--------------+     +--------------+     +--------------+
|Knowledge.vue |---->|  POST /api/   |---->|  Gateway     |
| 文本/文件上传 |     | knowledge/add |     | proxy_knowledge
+--------------+     +--------------+     +------+-------+
                                                  |
                       +--------------------------+
                       v
              +----------------+
              |   Agent QA     |
              | /knowledge/add |
              +--------+-------+
                       |
         +-------------+-------------+
         |             |             |
         v             v             v
    +--------+   +--------+   +--------+
    |ChromaDB|   | MySQL  |   |段落分块 |
    |批量写入 |   |knowledge|   |批量生成 |
    |用户隔离 |   |_items  |   | IDs    |
    +--------+   +--------+   +--------+
         |
         v
    +----------------+
    | 删除时同步清理  |
    | MySQL + Chroma |
    +----------------+
```

#### 2.5.2 前端实现

**文件：`frontend/src/views/Knowledge.vue`**

```vue
<template>
  <div class="page-container">
    <div class="knowledge-header">
      <h2>知识库</h2>
      <p class="subtitle">添加学习资料，AI 将基于知识库为你解答问题</p>
    </div>

    <div class="add-section">
      <el-form :model="addForm" label-position="top" class="add-form">
        <el-form-item label="知识内容">
          <el-input v-model="addForm.content" type="textarea" :rows="4" placeholder="输入知识内容..." />
        </el-form-item>
        <el-form-item label="知识库名称 (collection_name)">
          <el-input v-model="addForm.collection_name" placeholder="输入 collection_name" />
          <div class="collection-hint">只能使用字母、数字、下划线、中划线</div>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="adding" :disabled="!addForm.content || !addForm.collection_name" @click="handleAdd">
            <el-icon class="btn-icon"><Plus /></el-icon>添加
          </el-button>
        </el-form-item>
      </el-form>

      <el-upload class="upload-area" drag action="/api/knowledge/add/file"
        :headers="uploadHeaders" :data="{ collection_name: addForm.collection_name }"
        :on-success="handleUploadSuccess" :on-error="handleUploadError" accept=".txt,.md">
        <el-icon class="el-icon--upload"><upload-filled /></el-icon>
        <div class="el-upload__text">拖拽文件到此处，或 <em>点击上传</em></div>
        <template #tip>
          <div class="el-upload__tip">支持 .txt / .md 格式文件</div>
        </template>
      </el-upload>
    </div>

    <div class="search-section">
      <div class="search-box">
        <el-input v-model="searchQuery" placeholder="输入关键词搜索知识库..." class="search-input" @keyup.enter="handleSearch" clearable>
          <template #append>
            <el-button @click="handleSearch"><el-icon><Search /></el-icon></el-button>
          </template>
        </el-input>
      </div>

      <div v-if="searching" class="search-loading">
        <el-icon class="is-loading"><Loading /></el-icon><span>正在搜索...</span>
      </div>

      <div v-else-if="searchResults.length > 0" class="search-results">
        <div class="results-header">
          <span class="results-count">找到 {{ searchResults.length }} 条相关结果</span>
        </div>
        <div v-for="(item, index) in searchResults" :key="index" class="result-card">
          <div class="result-rank">#{{ index + 1 }}</div>
          <div class="result-content">
            <div class="result-text">{{ item.content }}</div>
            <div class="result-meta">
              <el-tag size="small" type="info" v-if="item.metadata && item.metadata.filename">{{ item.metadata.filename }}</el-tag>
              <el-tag size="small" type="success" v-if="item.distance !== null">相关度: {{ ((1 - item.distance) * 100).toFixed(1) }}%</el-tag>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, UploadFilled, Search, Loading } from '@element-plus/icons-vue'
import { addKnowledgeText, searchKnowledge } from '@/api/knowledge'

const addForm = ref({ content: '', collection_name: 'default' })
const adding = ref(false)
const searchQuery = ref('')
const searchResults = ref([])
const searching = ref(false)
const hasSearched = ref(false)

const token = localStorage.getItem('token')
const uploadHeaders = computed(() => ({ Authorization: `Bearer ${token}` }))

const handleAdd = async () => {
  if (!addForm.value.content || !addForm.value.collection_name) return
  const name = addForm.value.collection_name.trim()
  const validNameRegex = /^[a-zA-Z0-9][a-zA-Z0-9_.-]*[a-zA-Z0-9]$/
  if (!validNameRegex.test(name)) {
    ElMessage.error('知识库名称只能包含字母、数字、下划线、中划线')
    return
  }
  adding.value = true
  try {
    await addKnowledgeText({
      text: addForm.value.content,
      collection_name: addForm.value.collection_name,
    })
    ElMessage.success('知识添加成功')
    addForm.value.content = ''
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '添加失败')
  } finally {
    adding.value = false
  }
}

const handleSearch = async () => {
  if (!searchQuery.value.trim()) {
    searchResults.value = []
    hasSearched.value = false
    return
  }
  searching.value = true
  hasSearched.value = true
  try {
    const res = await searchKnowledge({
      query: searchQuery.value.trim(),
      collection_name: addForm.value.collection_name,
      n_results: 5,
    })
    searchResults.value = res.results || []
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '搜索失败')
    searchResults.value = []
  } finally {
    searching.value = false
  }
}
</script>
```

**文件：`frontend/src/api/knowledge.js`**

```javascript
import request from './request'

export const addKnowledgeText = (data) => {
  return request({ url: '/knowledge/add/text', method: 'post', data })
}

export const searchKnowledge = (params) => {
  return request({ url: '/knowledge/search', method: 'get', params })
}
```

#### 2.5.3 后端实现

**文件：`backend/common/chroma_client.py`**

```python
import chromadb
import uuid
from backend.config.settings import settings

class ChromaClient:
    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is None:
            self._client = chromadb.HttpClient(
                host=settings.CHROMA_HOST,    # chromadb
                port=settings.CHROMA_PORT,    # 8000
                ssl=False,
            )
        return self._client

    def get_or_create_collection(self, collection_name: str):
        client = self._get_client()
        return client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},    # 余弦相似度
        )

    def add_texts(self, collection_name, texts, metadatas=None, ids=None):
        """批量添加文本到集合"""
        if ids is None:
            ids = [str(uuid.uuid4()) for _ in texts]
        collection = self.get_or_create_collection(collection_name)
        collection.add(documents=texts, metadatas=metadatas, ids=ids)
        return ids

    def search(self, collection_name, query_text, n_results=5):
        collection = self.get_or_create_collection(collection_name)
        results = collection.query(query_texts=[query_text], n_results=n_results)
        return results

    def delete_collection(self, collection_name: str) -> None:
        client = self._get_client()
        client.delete_collection(name=collection_name)

    def list_collections(self):
        client = self._get_client()
        collections = client.list_collections()
        return [c.name for c in collections]

chroma_client = ChromaClient()
```

**文件：`backend/agent_qa/main.py` - 知识库路由**

```python
from fastapi import UploadFile, File, Query
from sqlalchemy import select

# ============================================================
# 关键优化 3：ChromaDB 批量写入（长文本按段落分块）
# ============================================================
@app.post("/knowledge/add/text")
async def add_text_to_knowledge(request, x_user_id: int = Header(...)):
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="文本内容不能为空")

    # 解析用户指定的 collection_name，生成用户隔离的 collection
    user_collection = _get_user_collection(x_user_id, request.collection_name)

    # 批量写入优化：将长文本按段落分割，批量添加
    paragraphs = [p.strip() for p in request.text.split('\n\n') if p.strip()]
    if not paragraphs:
        paragraphs = [request.text.strip()]

    # 批量生成 IDs
    item_ids = [str(uuid.uuid4()) for _ in paragraphs]
    metadatas = [{"user_id": str(x_user_id), "paragraph_index": i} for i in range(len(paragraphs))]

    # 批量添加到 ChromaDB（单次调用，减少网络往返）
    chroma_client.add_texts(
        collection_name=user_collection,
        texts=paragraphs,
        metadatas=metadatas,
        ids=item_ids,
    )

    # 同时写入 MySQL knowledge_items 表（记录第一条作为代表）
    session = await get_db_session()
    try:
        knowledge_item = KnowledgeItem(
            user_id=x_user_id,
            collection_name=user_collection,
            content=request.text[:500] + ("..." if len(request.text) > 500 else ""),
            chroma_id=item_ids[0],
        )
        session.add(knowledge_item)
        await session.commit()
        await session.refresh(knowledge_item)
        db_id = knowledge_item.id
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()

    return {
        "message": f"文本已添加到知识库（共 {len(paragraphs)} 个段落）",
        "chroma_ids": item_ids,
        "db_id": db_id,
        "collection_name": user_collection,
    }

@app.post("/knowledge/add/file")
async def add_file_to_knowledge(file: UploadFile = File(...), collection_name: str = Query(None), x_user_id: int = Header(...)):
    content_bytes = await file.read()
    text_content = _parse_file_content(file.filename, content_bytes)

    user_collection = _get_user_collection(x_user_id, collection_name)

    # 批量写入优化：按段落分块
    paragraphs = [p.strip() for p in text_content.split('\n\n') if p.strip()]
    if not paragraphs:
        paragraphs = [text_content.strip()]

    item_ids = [str(uuid.uuid4()) for _ in paragraphs]
    metadatas = [
        {"user_id": str(x_user_id), "filename": file.filename, "paragraph_index": i}
        for i in range(len(paragraphs))
    ]

    chroma_client.add_texts(
        collection_name=user_collection,
        texts=paragraphs,
        metadatas=metadatas,
        ids=item_ids,
    )

    session = await get_db_session()
    try:
        knowledge_item = KnowledgeItem(
            user_id=x_user_id,
            collection_name=user_collection,
            content=text_content[:500] + ("..." if len(text_content) > 500 else ""),
            filename=file.filename,
            chroma_id=item_ids[0],
        )
        session.add(knowledge_item)
        await session.commit()
        await session.refresh(knowledge_item)
        db_id = knowledge_item.id
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()

    return {
        "message": f"文件 '{file.filename}' 已添加到知识库（共 {len(paragraphs)} 个段落）",
        "chroma_ids": item_ids,
        "db_id": db_id,
        "collection_name": user_collection,
    }

# 搜索知识库
@app.get("/knowledge/search")
async def search_knowledge(query: str, collection_name: str = None, n_results: int = 5, x_user_id: int = Header(...)):
    user_collection = _get_user_collection(x_user_id, collection_name)
    results = chroma_client.search(
        collection_name=user_collection,
        query_text=query,
        n_results=n_results,
    )
    formatted = []
    if results and results.get("documents"):
        documents = results["documents"]
        metadatas = results.get("metadatas", [[] for _ in documents])
        distances = results.get("distances", [[] for _ in documents])
        ids = results.get("ids", [[] for _ in documents])
        for i, doc_list in enumerate(documents):
            for j, doc in enumerate(doc_list):
                meta = metadatas[i][j] if i < len(metadatas) and j < len(metadatas[i]) else {}
                distance = distances[i][j] if i < len(distances) and j < len(distances[i]) else None
                doc_id = ids[i][j] if i < len(ids) and j < len(ids[i]) else None
                formatted.append({"id": doc_id, "content": doc, "metadata": meta, "distance": distance})
    return { "results": formatted }

# ============================================================
# 关键优化 5：删除知识库条目时同步清理 ChromaDB 向量数据
# ============================================================
@app.delete("/knowledge/{item_id}")
async def delete_knowledge_item(item_id: int, x_user_id: int = Header(...)):
    session = await get_db_session()
    try:
        result = await session.execute(
            select(KnowledgeItem).where(
                KnowledgeItem.id == item_id,
                KnowledgeItem.user_id == x_user_id,
            )
        )
        item = result.scalar_one_or_none()
        if not item:
            raise HTTPException(status_code=404, detail="知识库条目不存在")

        # 同步从 ChromaDB 删除对应的向量数据
        try:
            collection = chroma_client.get_or_create_collection(item.collection_name)
            collection.delete(ids=[item.chroma_id])
        except Exception as ce:
            logger.warning(f"Failed to delete from ChromaDB (may already be deleted): {ce}")

        await session.delete(item)
        await session.commit()
        return { "message": "知识库条目已删除" }
    except HTTPException:
        raise
    finally:
        await session.close()
```

---

### 链路 6：Redis 限流链路

#### 2.6.1 链路流程图

```
用户请求 API
       |
       v
+--------------+     +--------------+     +--------------+
|  任意请求     |---->|  Gateway     |---->| 限流中间件   |
| /api/xxx     |     |              |     | rate_limit   |
+--------------+     +--------------+     +------+-------+
                                                  |
                       +--------------------------+
                       v
              +----------------+
              |   Redis 滑动窗口 |
              |  zremrangebyscore|
              |  zadd / zcard   |
              +--------+-------+
                       |
              +--------+--------+
              |                 |
              v                 v
        +----------+    +----------+
        | 未超限   |    | 已超限   |
        |继续处理  |    |返回 429 |
        +----------+    +----------+
```

#### 2.6.2 后端实现

**文件：`backend/gateway/main.py` - 限流中间件**

```python
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """
    Redis 滑动窗口限流中间件
    对 /api/ 路径进行限流
    """
    if not request.url.path.startswith("/api/"):
        return await call_next(request)

    # 获取限流 key（优先用户 ID，其次 IP）
    rate_key = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        try:
            token = auth_header[7:]
            user_id = JWTAuth.get_user_id_from_token(token)
            rate_key = f"user:{user_id}"
        except Exception:
            pass

    if not rate_key:
        rate_key = f"ip:{request.client.host}"

    # 检查限流（Redis 可能尚未连接，跳过限流）
    client = redis_client.client
    if client is None:
        return await call_next(request)

    is_limited = await redis_client.is_rate_limited(
        key=rate_key,
        window=settings.RATE_LIMIT_WINDOW,          # 60秒
        max_requests=settings.RATE_LIMIT_MAX_REQUESTS,  # 100次
    )

    if is_limited:
        limit_info = await redis_client.get_rate_limit_info(rate_key)
        return JSONResponse(
            status_code=429,
            content={
                "detail": "请求过于频繁，请稍后再试",
                "limit_info": limit_info,
            },
        )

    response = await call_next(request)
    return response
```

**文件：`backend/common/redis_client.py`**

```python
import json
import time
import redis.asyncio as redis
from backend.config.settings import settings

class RedisClient:
    _instance = None
    _pool = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def connect(self):
        if self._pool is None:
            self._pool = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                password=settings.REDIS_PASSWORD,
                db=settings.REDIS_DB,
                max_connections=settings.REDIS_POOL_SIZE,    # 50
                decode_responses=True,
            )

    async def close(self):
        if self._pool:
            await self._pool.close()
            self._pool = None

    @property
    def client(self):
        return self._pool

    # ==================== 限流功能（滑动窗口）====================
    async def is_rate_limited(self, key: str, window: int = 60, max_requests: int = 100) -> bool:
        """滑动窗口限流检查"""
        now = time.time()
        window_start = now - window
        redis_key = f"rate_limit:{key}"

        pipe = self.client.pipeline()
        # 1. 移除窗口外的旧记录
        pipe.zremrangebyscore(redis_key, 0, window_start)
        # 2. 添加当前请求时间戳
        pipe.zadd(redis_key, {str(now): now})
        # 3. 统计窗口内请求数
        pipe.zcard(redis_key)
        # 4. 设置 key 过期时间
        pipe.expire(redis_key, window + 1)

        results = await pipe.execute()
        current_count = results[2]

        if current_count > max_requests:
            # 超限则移除刚添加的记录
            await self.client.zrem(redis_key, str(now))
            return True
        return False

    async def get_rate_limit_info(self, key: str, window: int = 60) -> dict:
        now = time.time()
        window_start = now - window
        redis_key = f"rate_limit:{key}"
        count = await self.client.zcount(redis_key, window_start, now)
        ttl = await self.client.ttl(redis_key)
        return {
            "current_requests": count,
            "max_requests": settings.RATE_LIMIT_MAX_REQUESTS,
            "window": window,
            "ttl": ttl,
        }

    # ==================== 缓存功能 ====================
    async def cache_get(self, key: str):
        value = await self.client.get(f"cache:{key}")
        if value is None:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value

    async def cache_set(self, key: str, value, ttl: int = settings.CACHE_TTL):
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        await self.client.setex(f"cache:{key}", ttl, value)

    # ==================== Session 功能 ====================
    async def session_get(self, session_id: str):
        value = await self.client.get(f"session:{session_id}")
        if value is None:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None

    async def session_set(self, session_id: str, data: dict, ttl: int = settings.SESSION_TTL):
        await self.client.setex(f"session:{session_id}", ttl, json.dumps(data, ensure_ascii=False))

    async def ping(self) -> bool:
        try:
            return await self.client.ping()
        except Exception:
            return False

redis_client = RedisClient()
```

---

## 三、配置文件详解

### 3.1 Docker Compose 配置

**文件：`docker-compose.yml`**

```yaml
services:
  mysql:
    image: mysql:8.0
    container_name: smartnotes-mysql
    env_file:
      - .env
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD}
      MYSQL_DATABASE: ${MYSQL_DATABASE}
      MYSQL_USER: ${MYSQL_USER}
      MYSQL_PASSWORD: ${MYSQL_PASSWORD}
    ports:
      - "3307:3306"          # 宿主机 3307 映射到容器 3306
    volumes:
      - ./mysql-data:/var/lib/mysql    # 数据持久化
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:6.2-alpine
    container_name: smartnotes-redis
    ports:
      - "6379:6379"

  chromadb:
    image: chromadb/chroma:latest
    container_name: smartnotes-chroma
    ports:
      - "8005:8000"

  agent_note:    # 笔记整理 Agent
    build:
      context: .
      dockerfile: backend/Dockerfile
    container_name: smartnotes-agent_note
    env_file:
      - .env
    environment:
      - DASHSCOPE_API_KEY=${DASHSCOPE_API_KEY}
      - LLM_MODEL=${LLM_MODEL}
      - LLM_BASE_URL=${LLM_BASE_URL}
      - MYSQL_HOST=mysql
      - REDIS_URL=redis://redis:6379/0
    command: ["python", "-m", "uvicorn", "backend.agent_note.main:app", "--host", "0.0.0.0", "--port", "8001"]
    depends_on:
      mysql: { condition: service_healthy }
      redis: { condition: service_started }
    ports:
      - "8001:8001"

  agent_plan:    # 复习计划 Agent
    build:
      context: .
      dockerfile: backend/Dockerfile
    container_name: smartnotes-agent_plan
    env_file:
      - .env
    environment:
      - DASHSCOPE_API_KEY=${DASHSCOPE_API_KEY}
      - LLM_MODEL=${LLM_MODEL}
      - LLM_BASE_URL=${LLM_BASE_URL}
      - MYSQL_HOST=mysql
      - REDIS_URL=redis://redis:6379/0
    command: ["python", "-m", "uvicorn", "backend.agent_plan.main:app", "--host", "0.0.0.0", "--port", "8002"]
    depends_on:
      mysql: { condition: service_healthy }
      redis: { condition: service_started }
    ports:
      - "8002:8002"

  agent_qa:      # 问答 Agent
    build:
      context: .
      dockerfile: backend/Dockerfile
    container_name: smartnotes-agent_qa
    env_file:
      - .env
    environment:
      - DASHSCOPE_API_KEY=${DASHSCOPE_API_KEY}
      - LLM_MODEL=${LLM_MODEL}
      - LLM_BASE_URL=${LLM_BASE_URL}
      - MYSQL_HOST=mysql
      - REDIS_URL=redis://redis:6379/0
      - CHROMA_HOST=chromadb
      - CHROMA_PORT=8000
    command: ["python", "-m", "uvicorn", "backend.agent_qa.main:app", "--host", "0.0.0.0", "--port", "8003"]
    depends_on:
      mysql: { condition: service_healthy }
      redis: { condition: service_started }
      chromadb: { condition: service_started }
    ports:
      - "8003:8003"

  gateway:       # 统一网关
    build:
      context: .
      dockerfile: backend/Dockerfile
    container_name: smartnotes-gateway
    env_file:
      - .env
    environment:
      - DASHSCOPE_API_KEY=${DASHSCOPE_API_KEY}
      - LLM_MODEL=${LLM_MODEL}
      - LLM_BASE_URL=${LLM_BASE_URL}
      - MYSQL_HOST=mysql
      - REDIS_URL=redis://redis:6379/0
    command: ["python", "-m", "uvicorn", "backend.gateway.main:app", "--host", "0.0.0.0", "--port", "8000"]
    depends_on:
      agent_note: { condition: service_started }
      agent_plan: { condition: service_started }
      agent_qa: { condition: service_started }
    ports:
      - "8000:8000"

  frontend:      # 前端 Nginx
    build:
      context: ./frontend
      dockerfile: Dockerfile
    container_name: smartnotes-frontend
    ports:
      - "80:80"
    depends_on:
      - gateway

networks:
  default:
    driver: bridge
```

### 3.2 环境变量配置

**文件：`backend/config/settings.py`**

```python
import os

class Settings:
    # LLM 配置（百炼 qwen3.7-plus）
    LLM_MODEL: str = os.getenv("LLM_MODEL", "qwen3.7-plus")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    DASHSCOPE_API_KEY: str = os.getenv("DASHSCOPE_API_KEY", "")
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.7"))
    LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "4096"))
    LLM_TIMEOUT: int = int(os.getenv("LLM_TIMEOUT", "60"))

    # MySQL 配置
    MYSQL_HOST: str = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_PORT: int = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_USER: str = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD: str = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DATABASE: str = os.getenv("MYSQL_DATABASE", "smartnotes")
    MYSQL_POOL_SIZE: int = int(os.getenv("MYSQL_POOL_SIZE", "10"))
    MYSQL_POOL_OVERFLOW: int = int(os.getenv("MYSQL_POOL_OVERFLOW", "20"))
    MYSQL_POOL_TIMEOUT: int = int(os.getenv("MYSQL_POOL_TIMEOUT", "30"))

    # Redis 配置
    REDIS_URL: str = os.getenv("REDIS_URL", "")
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD") or None
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    REDIS_POOL_SIZE: int = int(os.getenv("REDIS_POOL_SIZE", "50"))

    # JWT 配置
    JWT_SECRET: str = os.getenv("JWT_SECRET", "smartnotes-secret-key-change-in-production")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_EXPIRE_HOURS: int = int(os.getenv("JWT_EXPIRE_HOURS", "24"))

    # 限流配置
    RATE_LIMIT_WINDOW: int = int(os.getenv("RATE_LIMIT_WINDOW", "60"))      # 秒
    RATE_LIMIT_MAX_REQUESTS: int = int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "100"))

    # 缓存配置
    CACHE_TTL: int = int(os.getenv("CACHE_TTL", "3600"))      # 秒
    SESSION_TTL: int = int(os.getenv("SESSION_TTL", "86400")) # 秒

    # ChromaDB 配置
    CHROMA_HOST: str = os.getenv("CHROMA_HOST", "localhost")
    CHROMA_PORT: int = int(os.getenv("CHROMA_PORT", "8000"))

    # 服务地址配置
    AGENT_NOTE_HOST: str = os.getenv("AGENT_NOTE_HOST", "agent_note")
    AGENT_NOTE_PORT: int = int(os.getenv("AGENT_NOTE_PORT", "8001"))
    AGENT_PLAN_HOST: str = os.getenv("AGENT_PLAN_HOST", "agent_plan")
    AGENT_PLAN_PORT: int = int(os.getenv("AGENT_PLAN_PORT", "8002"))
    AGENT_QA_HOST: str = os.getenv("AGENT_QA_HOST", "agent_qa")
    AGENT_QA_PORT: int = int(os.getenv("AGENT_QA_PORT", "8003"))
    GATEWAY_PORT: int = int(os.getenv("GATEWAY_PORT", "8000"))

    @classmethod
    def validate(cls):
        if not cls.DASHSCOPE_API_KEY:
            raise ValueError("DASHSCOPE_API_KEY 环境变量未设置")
        if not cls.MYSQL_PASSWORD:
            raise ValueError("MYSQL_PASSWORD 环境变量未设置")

    @property
    def mysql_url(self) -> str:
        return f"mysql+aiomysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}?charset=utf8mb4"

    @property
    def mysql_sync_url(self) -> str:
        return f"mysql+pymysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}?charset=utf8mb4"

settings = Settings()
```

### 3.3 Vite 配置

**文件：`frontend/vite.config.js`**

```javascript
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src')    // 路径别名 @ -> src
    }
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',  // 开发时代理到 Gateway
        changeOrigin: true
      }
    }
  }
})
```

---

## 四、面试常见问题与源码对应

### Q1：用户认证是如何实现的？

**答**：采用 **JWT Token + bcrypt 密码加密** 方案：

1. **注册时**：`gateway/main.py` 使用 `bcrypt.hashpw()` 加密密码存入 MySQL
2. **登录时**：查询数据库后用 `bcrypt.checkpw()` 验证密码
3. **登录成功**：`jwt_auth.py` 生成 JWT Token，包含 `user_id`、`username`、`exp` 过期时间
4. **请求时**：前端在 `request.js` 拦截器中自动附加 `Authorization: Bearer <token>`
5. **验证时**：`JWTAuth.get_current_user()` 解码 Token，支持 Header 和 Cookie 两种方式获取

**关键源码**：
- `backend/gateway/main.py` 第 89-178 行（注册/登录接口）
- `backend/common/jwt_auth.py` 第 20-115 行（JWT 创建/验证/解码）
- `frontend/src/api/request.js` 第 12-61 行（Axios 拦截器）

### Q2：流式输出是如何实现的？

**答**：采用 **HTTP 流式响应** 的逐字输出方案：

1. **前端**：使用原生 `fetch` + `response.body.getReader()` 读取流，通过 `TextDecoder` 解码
2. **Gateway**：使用 `_proxy_stream_request()` 将流从 Agent 透传给前端，设置 `X-Accel-Buffering: no` 禁用 Nginx 缓冲
3. **Agent**：使用 `StreamingResponse` 包装异步生成器
4. **Chain 层**：调用 `chain.astream()` 获取 LLM 流式输出
5. **LLM 层**：`ChatOpenAI(streaming=True)` 启用流式模式

**关键源码**：
- `frontend/src/views/Note.vue` 第 75-120 行（fetch 流式读取）
- `backend/gateway/main.py` 第 275-324 行（`_proxy_stream_request` 流式代理）
- `backend/chains/note_chain.py` 第 75-93 行（`organize_stream` 流式链）

### Q3：RAG 检索是如何工作的？

**答**：采用 **ChromaDB 向量数据库** 实现语义检索：

1. **用户上传文本时**：`chroma_client.add_texts()` 自动进行 Embedding 并存储到用户隔离的 collection
2. **用户提问时**：`chroma_client.search()` 将问题向量化，计算余弦相似度，返回最相关的 3-5 条结果
3. **检索到相关文档后**：拼接为 `context` 传入 LLM 提示词模板
4. **LLM 基于检索到的知识生成回答**
5. **问答结果自动保存回 ChromaDB**，形成知识闭环

**关键源码**：
- `backend/common/chroma_client.py` 第 16-106 行（ChromaDB HttpClient 封装）
- `backend/agent_qa/main.py` 第 200-212 行（自动检索用户隔离 collection）
- `backend/chains/qa_chain.py` 第 16-47 行（RAG Prompt 模板）

### Q4：限流是如何实现的？

**答**：采用 **Redis 滑动窗口算法**：

1. 使用 Redis 有序集合（ZSET）存储每个请求的时间戳
2. 每次请求时通过 Pipeline 原子执行：移除窗口外旧记录 -> 添加当前记录 -> 统计窗口内数量 -> 设置过期时间
3. 超过阈值则返回 429，否则继续处理
4. 限流 key 优先使用用户 ID（从 JWT Token 解析），未登录则使用 IP 地址

**关键源码**：
- `backend/gateway/main.py` 第 193-238 行（限流中间件）
- `backend/common/redis_client.py` 第 87-140 行（`is_rate_limited` 滑动窗口实现）

### Q5：知识库按用户隔离是如何实现的？

**答**：通过 **collection_name 自动绑定 user_id** 实现：

1. 用户传入 `collection_name` 时，后端自动拼接为 `user_{id}_{name}` 格式
2. 未传入时使用默认的 `user_{id}_default`
3. ChromaDB 搜索、添加、删除操作均使用用户隔离后的 collection 名称
4. 删除知识库条目时，同步从 ChromaDB 清理对应的向量数据，避免脏数据

**关键源码**：
- `backend/agent_qa/main.py` 第 103-111 行（`_get_user_collection` 用户隔离函数）
- `backend/agent_qa/main.py` 第 307-370 行（批量写入 + 用户隔离）
- `backend/agent_qa/main.py` 第 493-534 行（删除时同步清理 ChromaDB）

---

## 五、核心设计亮点

| 设计点 | 实现方式 | 源码位置 | 优化说明 |
|--------|----------|----------|----------|
| 统一网关 | FastAPI + 路由转发 + 流式透传 | `gateway/main.py` | 前端只与 8000 通信，Gateway 代理到各 Agent |
| JWT 认证 | PyJWT + bcrypt + 双渠道获取 | `common/jwt_auth.py` | 支持 Header 和 Cookie 两种方式 |
| 流式输出 | StreamingResponse + astream | `chains/*.py` | 全链路流式，用户体验接近实时 |
| Markdown 实时渲染 | marked + DOMPurify | `views/Note.vue`, `views/Plan.vue` | 支持标题/代码块/表格/引用，防 XSS |
| RAG 检索 | ChromaDB + 余弦相似度 | `common/chroma_client.py` | 语义检索，返回相关度百分比 |
| 用户隔离 | collection_name 绑定 user_id | `agent_qa/main.py` | 格式 `user_{id}_{name}`，数据安全隔离 |
| 模型版本缓存 | 缓存 key 包含 LLM_MODEL | `agent_qa/main.py` | 避免模型升级后缓存失效 |
| 批量写入优化 | 长文本按段落分块 + 批量 add | `agent_qa/main.py` | 减少网络往返，提升写入性能 |
| 删除同步清理 | MySQL 删除 + ChromaDB delete | `agent_qa/main.py` | 避免向量库脏数据 |
| 滑动窗口限流 | Redis ZSET + Pipeline | `common/redis_client.py` | 精确控制请求频率 |
| 异步数据库 | SQLAlchemy + aiomysql | `common/database.py` | 连接池管理，支持高并发 |
| 单例模式 | `__new__` + `_instance` | `services/llm_service.py` | LLM 实例全局复用 |
| 生命周期管理 | `asynccontextmanager` | 各 `main.py` | 优雅启停，资源释放 |
| 思考中动画 | CSS 动画 + Vue 条件渲染 | `views/QA.vue` | 三个跳动圆点，提升等待体验 |
| 打字机光标 | CSS blink 动画 | `views/QA.vue` | 竖线闪烁，模拟打字效果 |
| 复习计划修复 | 移除 chunk.trim() 过滤 | `views/Plan.vue` | 确保流式内容完整不丢失 |
| 响应拦截 | Axios interceptors | `api/request.js` | 统一错误处理，自动跳转登录 |
| 状态管理 | Pinia + localStorage | `stores/auth.js` | 刷新不丢失登录状态 |
| 路由守卫 | Vue Router beforeEach | `router/index.js` | 未登录自动拦截 |

---

> 文档生成时间：2026-06-18
> 项目版本：v2.1.0
