<template>
  <div class="page-container">
    <!-- 左侧边栏 -->
    <div
      class="sidebar"
      :class="{ collapsed: sidebarCollapsed }"
    >
      <div class="sidebar-header">
        <span v-if="!sidebarCollapsed" class="sidebar-title">会话列表</span>
        <el-button
          text
          class="collapse-btn"
          @click="toggleSidebar"
        >
          <el-icon size="18">
            <component :is="sidebarCollapsed ? Expand : Fold" />
          </el-icon>
        </el-button>
      </div>

      <div class="session-list" v-if="!sidebarCollapsed">
        <div
          v-for="s in sessions"
          :key="s.session_id"
          :class="['session-item', { active: currentSessionId === s.session_id }]"
          @click="switchSession(s.session_id)"
        >
          <div class="session-info">
            <div class="session-name">{{ s.title || `会话 ${s.session_id.slice(0, 8)}...` }}</div>
            <div class="session-meta">
              <span class="msg-count">{{ s.message_count || 0 }} 条消息</span>
              <span class="session-time">{{ formatTime(s.updated_at) }}</span>
            </div>
          </div>
          <el-button
            class="delete-btn"
            text
            size="small"
            @click.stop="deleteSession(s.session_id)"
          >
            <el-icon size="14"><Delete /></el-icon>
          </el-button>
        </div>
        <div v-if="sessions.length === 0" class="no-sessions">
          暂无会话
        </div>
      </div>

      <div class="sidebar-footer" v-if="!sidebarCollapsed">
        <el-button
          type="primary"
          class="new-session-btn"
          @click="createNewSession"
        >
          <el-icon><Plus /></el-icon>
          新会话
        </el-button>
      </div>
    </div>

    <!-- 主聊天区域 -->
    <div class="chat-wrapper">
      <div class="chat-header">
        <div class="header-title">
          <template v-if="currentSession">
            {{ currentSession.title || `会话 ${currentSession.session_id.slice(0, 8)}...` }}
          </template>
          <template v-else>新会话</template>
        </div>
        <div class="header-actions">
          <el-button
            v-if="sidebarCollapsed"
            text
            size="small"
            @click="toggleSidebar"
          >
            <el-icon size="16"><Expand /></el-icon>
          </el-button>
          <el-button
            text
            size="small"
            type="danger"
            @click="clearCurrentSession"
          >
            <el-icon size="16"><Delete /></el-icon>
            清空
          </el-button>
        </div>
      </div>

      <div class="chat-container">
        <div class="messages" ref="messagesRef">
          <div
            v-for="(msg, index) in messages"
            :key="index"
            :class="['message', msg.role]"
          >
            <div class="message-avatar">
              <el-icon size="20" :color="msg.role === 'user' ? '#00f0ff' : '#a855f7'">
                <component :is="msg.role === 'user' ? User : ChatDotRound" />
              </el-icon>
            </div>
            <div class="message-bubble">
              <!-- 思考中动画 -->
              <div v-if="msg.thinking" class="thinking-indicator">
                <span class="dot"></span>
                <span class="dot"></span>
                <span class="dot"></span>
              </div>
              <!-- 实际内容 - Markdown 渲染 -->
              <div v-else-if="msg.content" class="markdown-body" v-html="renderMarkdown(msg.content)"></div>
              <!-- 空内容占位（防止气泡塌陷） -->
              <div v-else class="empty-content">&nbsp;</div>
              <!-- 打字机光标 -->
              <span v-if="msg.streaming && !msg.thinking" class="typing-cursor">|</span>
            </div>
          </div>
          <div v-if="messages.length === 0" class="empty-state">
            <el-icon size="48" color="rgba(0, 240, 255, 0.3)"><ChatDotRound /></el-icon>
            <p>开始你的智能问答之旅</p>
            <span class="hint">输入问题，ReAct Agent 将自主决策并调用工具为你解答</span>
          </div>
        </div>

        <div class="input-area">
          <el-input
            v-model="question"
            type="textarea"
            :rows="2"
            placeholder="输入你的问题...（Agent 会自动决定是否需要搜索知识库、计算或联网）"
            class="chat-input"
            @keyup.enter.ctrl="handleAsk"
          />
          <el-button
            type="primary"
            class="send-btn"
            :loading="loading"
            :disabled="!question.trim()"
            @click="handleAsk"
          >
            <el-icon size="18"><Promotion /></el-icon>
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { ChatDotRound, User, Promotion, Plus, Delete, Fold, Expand } from '@element-plus/icons-vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

// 配置 marked
marked.setOptions({
  gfm: true,
  breaks: true,
  headerIds: false,
  mangle: false
})

const question = ref('')
const messages = ref([])
const loading = ref(false)
const messagesRef = ref()
const currentSessionId = ref('')
const sessions = ref([])
const sidebarCollapsed = ref(false)

const currentSession = computed(() => {
  return sessions.value.find(s => s.session_id === currentSessionId.value)
})

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

const toggleSidebar = () => {
  sidebarCollapsed.value = !sidebarCollapsed.value
}

const formatTime = (timestamp) => {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  const now = new Date()
  const diff = now - date
  const minutes = Math.floor(diff / 60000)
  const hours = Math.floor(diff / 3600000)
  const days = Math.floor(diff / 86400000)

  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes}分钟前`
  if (hours < 24) return `${hours}小时前`
  if (days < 7) return `${days}天前`
  return date.toLocaleDateString('zh-CN')
}

// ==================== 会话管理 ====================

const loadSessions = async () => {
  try {
    const token = localStorage.getItem('token')
    const resp = await fetch('/api/qa/sessions', {
      headers: { 'Authorization': `Bearer ${token}` }
    })
    if (resp.ok) {
      const data = await resp.json()
      sessions.value = data.sessions || []
    }
  } catch (e) {
    // 静默失败，不影响主功能
  }
}

const createNewSession = () => {
  const newId = crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
  currentSessionId.value = newId
  messages.value = []
  // 持久化到 localStorage，页面切换后恢复
  localStorage.setItem('qa_current_session_id', newId)
  ElMessage.success('已创建新会话')
}

const deleteSession = async (sessionId) => {
  if (!sessionId) return
  try {
    const token = localStorage.getItem('token')
    await fetch(`/api/qa/sessions/${sessionId}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${token}` }
    })
    await loadSessions()
    // 如果删除的是当前会话，自动创建新会话
    if (currentSessionId.value === sessionId) {
      createNewSession()
    }
    ElMessage.success('会话已删除')
  } catch (e) {
    ElMessage.error('删除会话失败')
  }
}

const clearCurrentSession = async () => {
  if (!currentSessionId.value) {
    messages.value = []
    ElMessage.success('已清空当前会话')
    return
  }
  try {
    const token = localStorage.getItem('token')
    await fetch(`/api/qa/sessions/${currentSessionId.value}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${token}` }
    })
    messages.value = []
    await loadSessions()
    ElMessage.success('会话已删除')
  } catch (e) {
    messages.value = []
    ElMessage.success('已清空当前会话')
  }
  // 清空后自动创建新会话，避免下次提问时 session_id 为空
  createNewSession()
}

const switchSession = async (sessionId) => {
  if (!sessionId) {
    messages.value = []
    currentSessionId.value = ''
    localStorage.removeItem('qa_current_session_id')
    return
  }
  currentSessionId.value = sessionId
  localStorage.setItem('qa_current_session_id', sessionId)
  messages.value = []

  // 从后端加载该会话的历史消息
  try {
    const token = localStorage.getItem('token')
    const resp = await fetch(`/api/qa/sessions/${sessionId}/history`, {
      headers: { 'Authorization': `Bearer ${token}` }
    })
    if (resp.ok) {
      const data = await resp.json()
      if (data.history && Array.isArray(data.history)) {
        messages.value = data.history.map(h => ({
          role: h.role,
          content: h.content,
          streaming: false,
          thinking: false
        }))
        await nextTick()
        scrollToBottom()
      }
    } else if (resp.status === 401) {
      ElMessage.error('登录已过期，请重新登录')
      localStorage.removeItem('token')
      window.location.href = '/login'
      return
    }
  } catch (e) {
    // 加载失败不影响切换，只是没有历史消息
    console.error('加载历史消息失败:', e)
  }
}

// ==================== 问答核心 ====================

const handleAsk = async () => {
  if (!question.value.trim() || loading.value) return

  const userQuestion = question.value.trim()
  messages.value.push({ role: 'user', content: userQuestion })
  question.value = ''
  loading.value = true
  await nextTick()
  scrollToBottom()

  // 添加 assistant 消息占位（用于流式显示）
  const assistantMsg = {
    role: 'assistant',
    content: '',
    streaming: true,
    thinking: true
  }
  messages.value.push(assistantMsg)
  const assistantIndex = messages.value.length - 1
  await nextTick()
  scrollToBottom()

  try {
    const token = localStorage.getItem('token')
    const response = await fetch('/api/qa/ask/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({
        question: userQuestion,
        use_agent: true,
        session_id: currentSessionId.value
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
    let buffer = ''
    let hasContent = false
    let processInfo = ''  // 过程信息（thought/action/observation）
    let tokenContent = ''  // LLM 流式 token 累积

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      const chunk = decoder.decode(value, { stream: true })
      buffer += chunk

      // 解析 SSE 格式的数据行
      const lines = buffer.split('\n')
      buffer = lines.pop() || '' // 保留未完整的最后一行

      for (const line of lines) {
        const trimmed = line.trim()
        if (!trimmed.startsWith('data: ')) continue

        const dataStr = trimmed.slice(6).trim()
        if (dataStr === '[DONE]') {
          messages.value[assistantIndex].streaming = false
          messages.value[assistantIndex].thinking = false
          continue
        }

        try {
          const event = JSON.parse(dataStr)

          // 处理 session_id 事件
          if (event.type === 'session_id') {
            if (event.session_id && event.session_id !== currentSessionId.value) {
              currentSessionId.value = event.session_id
              localStorage.setItem('qa_current_session_id', event.session_id)
            }
            continue
          }

          // 收到第一个有效内容时，移除 thinking 状态
          if (!hasContent && event.content) {
            hasContent = true
            messages.value[assistantIndex].thinking = false
          }

          if (event.type === 'token') {
            // 流式 token：实时追加显示（打字机效果）
            tokenContent += event.content
            // 组合显示：过程信息 + 当前 token 流
            messages.value[assistantIndex].content = processInfo + tokenContent
          } else if (event.type === 'thought') {
            // 思考过程：记录到过程信息
            processInfo += `💭 **思考**: ${event.content}\n\n`
            messages.value[assistantIndex].content = processInfo + tokenContent
          } else if (event.type === 'action') {
            // 工具调用：记录到过程信息
            processInfo += `🔧 **工具**: ${event.content}\n\n`
            messages.value[assistantIndex].content = processInfo + tokenContent
          } else if (event.type === 'observation') {
            // 观察结果：记录到过程信息
            processInfo += `👁️ **观察**: ${event.content}\n\n`
            messages.value[assistantIndex].content = processInfo + tokenContent
          } else if (event.type === 'final_answer') {
            // 最终回答：替换为干净内容（去掉过程信息中的 ReAct 标记）
            messages.value[assistantIndex].content = event.content
            messages.value[assistantIndex].streaming = false
            messages.value[assistantIndex].thinking = false
          }

          await nextTick()
          scrollToBottom()
        } catch (e) {
          // JSON 解析失败，忽略
        }
      }
    }

    // 处理缓冲区中剩余的内容
    if (buffer.trim().startsWith('data: ')) {
      const dataStr = buffer.trim().slice(6).trim()
      if (dataStr && dataStr !== '[DONE]') {
        try {
          const event = JSON.parse(dataStr)
          if (event.type === 'final_answer') {
            messages.value[assistantIndex].content = event.content
          }
        } catch (e) {}
      }
    }

    // 如果始终没有收到内容
    if (!hasContent) {
      messages.value[assistantIndex].thinking = false
      messages.value[assistantIndex].content = '抱歉，没有收到回复内容。'
    }

    // 问答完成后刷新会话列表
    await loadSessions()

  } catch (e) {
    messages.value[assistantIndex].thinking = false
    messages.value[assistantIndex].streaming = false
    messages.value[assistantIndex].content = '抱歉，回答时出错了: ' + e.message
  } finally {
    loading.value = false
    messages.value[assistantIndex].streaming = false
    messages.value[assistantIndex].thinking = false
    await nextTick()
    scrollToBottom()
  }
}

// 响应式：极小屏幕下自动折叠侧边栏
const checkScreenSize = () => {
  // 只在极小屏幕（< 480px）时自动折叠，避免误判
  if (window.innerWidth < 480) {
    sidebarCollapsed.value = true
  }
}

onMounted(async () => {
  await loadSessions()
  checkScreenSize()
  window.addEventListener('resize', checkScreenSize)

  const savedSessionId = localStorage.getItem('qa_current_session_id')
  if (savedSessionId) {
    // 检查这个 session 是否在会话列表中
    const sessionExists = sessions.value.some(s => s.session_id === savedSessionId)
    if (sessionExists) {
      currentSessionId.value = savedSessionId
      try {
        const token = localStorage.getItem('token')
        const resp = await fetch(`/api/qa/sessions/${savedSessionId}/history`, {
          headers: { 'Authorization': `Bearer ${token}` }
        })
        if (resp.ok) {
          const data = await resp.json()
          if (data.history && Array.isArray(data.history) && data.history.length > 0) {
            messages.value = data.history.map(h => ({
              role: h.role,
              content: h.content,
              streaming: false,
              thinking: false
            }))
            await nextTick()
            scrollToBottom()
            return
          }
        }
      } catch (e) {}
      // session 存在但历史为空，仍然使用该 session（可能是个新会话）
      return
    }
    // session 不在列表中，清除无效 localStorage
    localStorage.removeItem('qa_current_session_id')
  }
  // 没有有效会话，创建新会话
  createNewSession()
})
</script>

<style scoped>
.page-container {
  display: flex;
  height: calc(100vh - 64px);
  overflow: hidden;
}

/* ==================== 左侧边栏 ==================== */
.sidebar {
  width: 220px;
  min-width: 220px;
  background: rgba(15, 23, 42, 0.7);
  border-right: 1px solid rgba(0, 240, 255, 0.1);
  display: flex;
  flex-direction: column;
  transition: all 0.3s ease;
  overflow: hidden;
}

.sidebar.collapsed {
  width: 40px;
  min-width: 40px;
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid rgba(0, 240, 255, 0.08);
  height: 52px;
}

.sidebar-title {
  font-size: 15px;
  font-weight: 600;
  color: #e2e8f0;
}

.collapse-btn {
  color: #94a3b8;
  padding: 4px;
}

.collapse-btn:hover {
  color: #00f0ff;
}

.session-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.session-item {
  display: flex;
  align-items: center;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  margin-bottom: 4px;
  transition: all 0.2s ease;
  position: relative;
}

.session-item:hover {
  background: rgba(0, 240, 255, 0.06);
}

.session-item:hover .delete-btn {
  opacity: 1;
}

.session-item.active {
  background: rgba(0, 240, 255, 0.1);
  border: 1px solid rgba(0, 240, 255, 0.15);
}

.session-item.active .session-name {
  color: #00f0ff;
}

.session-info {
  flex: 1;
  min-width: 0;
  overflow: hidden;
}

.session-name {
  font-size: 13px;
  font-weight: 500;
  color: #e2e8f0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 2px;
}

.session-meta {
  display: flex;
  gap: 8px;
  font-size: 11px;
  color: #64748b;
}

.msg-count {
  color: #94a3b8;
}

.session-time {
  color: #64748b;
}

.delete-btn {
  opacity: 0;
  transition: opacity 0.2s ease;
  color: #64748b;
  padding: 2px;
  margin-left: 4px;
}

.delete-btn:hover {
  color: #ef4444;
}

.no-sessions {
  text-align: center;
  padding: 32px 16px;
  color: #64748b;
  font-size: 13px;
}

.sidebar-footer {
  padding: 12px 16px;
  border-top: 1px solid rgba(0, 240, 255, 0.08);
}

.new-session-btn {
  width: 100%;
  background: linear-gradient(135deg, #00f0ff 0%, #7c3aed 100%);
  border: none;
  border-radius: 10px;
  font-weight: 500;
}

.new-session-btn:hover {
  box-shadow: 0 4px 15px rgba(0, 240, 255, 0.3);
}

/* ==================== 主聊天区域 ==================== */
.chat-wrapper {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: rgba(15, 23, 42, 0.4);
}

.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  border-bottom: 1px solid rgba(0, 240, 255, 0.08);
  height: 52px;
  background: rgba(15, 23, 42, 0.5);
  flex-shrink: 0;
}

.header-title {
  font-size: 15px;
  font-weight: 600;
  color: #e2e8f0;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.chat-container {
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow: hidden;
}

.messages {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex: 1;
  gap: 12px;
  color: rgba(148, 163, 184, 0.6);
}

.empty-state p {
  font-size: 16px;
  font-weight: 500;
  margin: 0;
}

.empty-state .hint {
  font-size: 13px;
}

.message {
  display: flex;
  gap: 12px;
  max-width: 90%;
}

.message.user {
  align-self: flex-end;
  flex-direction: row-reverse;
}

.message.assistant {
  align-self: flex-start;
}

.message-avatar {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 240, 255, 0.08);
  border: 1px solid rgba(0, 240, 255, 0.15);
  flex-shrink: 0;
}

.message.user .message-avatar {
  background: rgba(0, 240, 255, 0.12);
}

.message-bubble {
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.6;
  position: relative;
  min-height: 20px;
  min-width: 40px;
}

.message.user .message-bubble {
  background: rgba(0, 240, 255, 0.12);
  color: #e2e8f0;
  border: 1px solid rgba(0, 240, 255, 0.15);
}

.message.assistant .message-bubble {
  background: rgba(124, 58, 237, 0.08);
  color: #cbd5e1;
  border: 1px solid rgba(124, 58, 237, 0.12);
}

/* 空内容占位 */
.empty-content {
  min-height: 20px;
  min-width: 20px;
}

/* Markdown 渲染样式 */
:deep(.markdown-body) {
  color: #cbd5e1;
  font-size: 14px;
  line-height: 1.7;
}

:deep(.markdown-body h1),
:deep(.markdown-body h2),
:deep(.markdown-body h3),
:deep(.markdown-body h4),
:deep(.markdown-body h5),
:deep(.markdown-body h6) {
  color: #e2e8f0;
  margin: 12px 0 8px;
  font-weight: 600;
  border-bottom: 1px solid rgba(0, 240, 255, 0.1);
  padding-bottom: 4px;
}

:deep(.markdown-body h1) { font-size: 20px; }
:deep(.markdown-body h2) { font-size: 17px; }
:deep(.markdown-body h3) { font-size: 15px; }

:deep(.markdown-body p) {
  margin: 6px 0;
  color: #cbd5e1;
}

:deep(.markdown-body strong) {
  color: #00f0ff;
  font-weight: 600;
}

:deep(.markdown-body ul),
:deep(.markdown-body ol) {
  padding-left: 20px;
  margin: 6px 0;
}

:deep(.markdown-body li) {
  margin: 3px 0;
}

:deep(.markdown-body code) {
  background: rgba(0, 240, 255, 0.08);
  color: #00f0ff;
  padding: 2px 5px;
  border-radius: 4px;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 12.5px;
}

:deep(.markdown-body pre) {
  background: rgba(15, 23, 42, 0.8);
  border: 1px solid rgba(0, 240, 255, 0.1);
  border-radius: 8px;
  padding: 10px 14px;
  overflow-x: auto;
  margin: 8px 0;
}

:deep(.markdown-body pre code) {
  background: transparent;
  padding: 0;
  color: #a5b4fc;
}

:deep(.markdown-body blockquote) {
  border-left: 3px solid rgba(0, 240, 255, 0.3);
  margin: 8px 0;
  padding: 6px 14px;
  background: rgba(0, 240, 255, 0.03);
  border-radius: 0 8px 8px 0;
}

:deep(.markdown-body blockquote p) {
  margin: 0;
  color: #94a3b8;
}

:deep(.markdown-body hr) {
  border: none;
  border-top: 1px solid rgba(0, 240, 255, 0.1);
  margin: 12px 0;
}

:deep(.markdown-body table) {
  width: 100%;
  border-collapse: collapse;
  margin: 8px 0;
  font-size: 12.5px;
}

:deep(.markdown-body th) {
  background: rgba(0, 240, 255, 0.06);
  color: #e2e8f0;
  padding: 6px 10px;
  text-align: left;
  border-bottom: 1px solid rgba(0, 240, 255, 0.15);
}

:deep(.markdown-body td) {
  padding: 6px 10px;
  border-bottom: 1px solid rgba(0, 240, 255, 0.08);
  color: #cbd5e1;
}

/* 思考中动画 */
.thinking-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 0;
}

.thinking-indicator .dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #a855f7;
  opacity: 0.4;
  animation: thinking-bounce 1.4s infinite ease-in-out;
}

.thinking-indicator .dot:nth-child(1) { animation-delay: 0s; }
.thinking-indicator .dot:nth-child(2) { animation-delay: 0.2s; }
.thinking-indicator .dot:nth-child(3) { animation-delay: 0.4s; }

@keyframes thinking-bounce {
  0%, 80%, 100% {
    transform: scale(0.6);
    opacity: 0.4;
  }
  40% {
    transform: scale(1);
    opacity: 1;
  }
}

.typing-cursor {
  display: inline-block;
  width: 2px;
  height: 18px;
  background: #00f0ff;
  margin-left: 4px;
  animation: blink 1s infinite;
  vertical-align: middle;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

.input-area {
  display: flex;
  gap: 12px;
  padding: 16px 20px;
  border-top: 1px solid rgba(0, 240, 255, 0.1);
  background: rgba(15, 23, 42, 0.6);
  flex-shrink: 0;
}

.chat-input :deep(.el-textarea__inner) {
  background: rgba(30, 41, 59, 0.6);
  border: 1px solid rgba(148, 163, 184, 0.2);
  color: #e2e8f0;
  border-radius: 12px;
  padding: 10px 14px;
  resize: none;
}

.chat-input :deep(.el-textarea__inner::placeholder) {
  color: rgba(148, 163, 184, 0.5);
}

.chat-input :deep(.el-textarea__inner:focus) {
  border-color: rgba(0, 240, 255, 0.4);
}

.send-btn {
  width: 44px;
  height: 44px;
  padding: 0;
  border-radius: 12px;
  background: linear-gradient(135deg, #00f0ff 0%, #7c3aed 100%);
  border: none;
  flex-shrink: 0;
  align-self: center;
}

.send-btn:hover {
  box-shadow: 0 4px 15px rgba(0, 240, 255, 0.3);
}

/* 响应式适配 */
@media (max-width: 768px) {
  .sidebar {
    position: absolute;
    z-index: 100;
    height: 100%;
    box-shadow: 2px 0 10px rgba(0, 0, 0, 0.3);
  }

  .sidebar.collapsed {
    transform: translateX(-100%);
    width: 280px;
    min-width: 280px;
  }

  .chat-wrapper {
    width: 100%;
  }
}
</style>
