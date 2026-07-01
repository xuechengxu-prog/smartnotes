<template>
  <div class="page-container">
    <div class="input-section">
      <el-input
        v-model="rawNote"
        type="textarea"
        :rows="8"
        placeholder="在此粘贴你的原始笔记内容..."
        class="dark-textarea"
      />
      <div class="actions">
        <el-button
          type="primary"
          size="large"
          :loading="loading"
          :disabled="!rawNote.trim()"
          @click="handleOrganize"
        >
          <el-icon class="btn-icon"><MagicStick /></el-icon>
          智能整理
        </el-button>
        <el-button
          size="large"
          :disabled="!result"
          @click="copyResult"
        >
          <el-icon class="btn-icon"><CopyDocument /></el-icon>
          复制结果
        </el-button>
      </div>
    </div>

    <div v-if="result || streaming" class="result-section">
      <div class="result-header">
        <el-icon size="18" color="#00f0ff"><DocumentChecked /></el-icon>
        <span>整理结果</span>
        <span v-if="streaming" class="typing-indicator">
          <span class="dot"></span>
          <span class="dot"></span>
          <span class="dot"></span>
        </span>
      </div>
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
marked.setOptions({
  gfm: true,
  breaks: true,
  headerIds: false,
  mangle: false
})

const rawNote = ref('')
const result = ref('')
const loading = ref(false)
const streaming = ref(false)

// 实时渲染 Markdown
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
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
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

<style scoped>
.page-container {
  max-width: 900px;
  margin: 0 auto;
}

.input-section {
  margin-bottom: 24px;
}

.dark-textarea :deep(.el-textarea__inner) {
  background: rgba(15, 23, 42, 0.6);
  border: 1px solid rgba(0, 240, 255, 0.15);
  color: #e2e8f0;
  font-size: 14px;
  line-height: 1.8;
  border-radius: 12px;
  padding: 16px;
}

.dark-textarea :deep(.el-textarea__inner::placeholder) {
  color: rgba(148, 163, 184, 0.5);
}

.dark-textarea :deep(.el-textarea__inner:focus) {
  border-color: rgba(0, 240, 255, 0.4);
  box-shadow: 0 0 15px rgba(0, 240, 255, 0.08);
}

.actions {
  display: flex;
  gap: 12px;
  margin-top: 16px;
}

.actions .el-button {
  border-radius: 10px;
  font-weight: 500;
}

.actions .el-button--primary {
  background: linear-gradient(135deg, #00f0ff 0%, #7c3aed 100%);
  border: none;
}

.btn-icon {
  margin-right: 6px;
}

.result-section {
  background: rgba(15, 23, 42, 0.5);
  border: 1px solid rgba(0, 240, 255, 0.12);
  border-radius: 12px;
  overflow: hidden;
}

.result-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 18px;
  background: rgba(0, 240, 255, 0.05);
  border-bottom: 1px solid rgba(0, 240, 255, 0.1);
  font-size: 14px;
  font-weight: 600;
  color: #e2e8f0;
}

.typing-indicator {
  display: flex;
  gap: 4px;
  margin-left: 8px;
}

.dot {
  width: 6px;
  height: 6px;
  background: #00f0ff;
  border-radius: 50%;
  animation: bounce 1.4s infinite ease-in-out both;
}

.dot:nth-child(1) { animation-delay: -0.32s; }
.dot:nth-child(2) { animation-delay: -0.16s; }

@keyframes bounce {
  0%, 80%, 100% { transform: scale(0); opacity: 0.5; }
  40% { transform: scale(1); opacity: 1; }
}

.result-content {
  padding: 18px;
}

/* Markdown 渲染样式 */
:deep(.markdown-body) {
  color: #cbd5e1;
  font-size: 14px;
  line-height: 1.8;
}

:deep(.markdown-body h1),
:deep(.markdown-body h2),
:deep(.markdown-body h3),
:deep(.markdown-body h4),
:deep(.markdown-body h5),
:deep(.markdown-body h6) {
  color: #e2e8f0;
  margin: 16px 0 10px;
  font-weight: 600;
  border-bottom: 1px solid rgba(0, 240, 255, 0.1);
  padding-bottom: 6px;
}

:deep(.markdown-body h1) { font-size: 22px; }
:deep(.markdown-body h2) { font-size: 18px; }
:deep(.markdown-body h3) { font-size: 16px; }

:deep(.markdown-body p) {
  margin: 8px 0;
  color: #cbd5e1;
}

:deep(.markdown-body strong) {
  color: #00f0ff;
  font-weight: 600;
}

:deep(.markdown-body ul),
:deep(.markdown-body ol) {
  padding-left: 24px;
  margin: 8px 0;
}

:deep(.markdown-body li) {
  margin: 4px 0;
}

:deep(.markdown-body code) {
  background: rgba(0, 240, 255, 0.08);
  color: #00f0ff;
  padding: 2px 6px;
  border-radius: 4px;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 13px;
}

:deep(.markdown-body pre) {
  background: rgba(15, 23, 42, 0.8);
  border: 1px solid rgba(0, 240, 255, 0.1);
  border-radius: 8px;
  padding: 12px 16px;
  overflow-x: auto;
  margin: 10px 0;
}

:deep(.markdown-body pre code) {
  background: transparent;
  padding: 0;
  color: #a5b4fc;
}

:deep(.markdown-body blockquote) {
  border-left: 3px solid rgba(0, 240, 255, 0.3);
  margin: 10px 0;
  padding: 8px 16px;
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
  margin: 16px 0;
}

:deep(.markdown-body table) {
  width: 100%;
  border-collapse: collapse;
  margin: 10px 0;
  font-size: 13px;
}

:deep(.markdown-body th) {
  background: rgba(0, 240, 255, 0.06);
  color: #e2e8f0;
  padding: 8px 12px;
  text-align: left;
  border-bottom: 1px solid rgba(0, 240, 255, 0.15);
}

:deep(.markdown-body td) {
  padding: 8px 12px;
  border-bottom: 1px solid rgba(0, 240, 255, 0.08);
  color: #cbd5e1;
}
</style>
