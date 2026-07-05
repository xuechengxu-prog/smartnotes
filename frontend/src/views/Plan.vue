<template>
  <div class="page-container">
    <div class="form-section">
      <el-form :model="form" label-position="top" class="plan-form">
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="科目">
              <el-input
                v-model="form.subject"
                placeholder="例如：高等数学"
                size="large"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="每日学习时长（小时）">
              <el-input-number
                v-model="form.daily_hours"
                :min="0.5"
                :max="12"
                :step="0.5"
                size="large"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="开始日期">
              <el-date-picker
                v-model="form.start_date"
                type="date"
                placeholder="选择开始日期"
                size="large"
                style="width: 100%"
                value-format="YYYY-MM-DD"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="结束日期">
              <el-date-picker
                v-model="form.end_date"
                type="date"
                placeholder="选择结束日期"
                size="large"
                style="width: 100%"
                value-format="YYYY-MM-DD"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item>
          <el-button
            type="primary"
            size="large"
            :loading="loading"
            :disabled="!canSubmit"
            @click="handleGenerate"
          >
            <el-icon class="btn-icon"><Calendar /></el-icon>
            生成复习计划
          </el-button>
        </el-form-item>
      </el-form>
    </div>

    <div v-if="result || streaming" class="result-section">
      <div class="result-header">
        <el-icon size="18" color="#6366f1"><DocumentChecked /></el-icon>
        <span>复习计划</span>
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
import { Calendar, DocumentChecked } from '@element-plus/icons-vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

// 配置 marked
marked.setOptions({
  gfm: true,
  breaks: true,
  headerIds: false,
  mangle: false
})

const form = ref({
  subject: '',
  start_date: '',
  end_date: '',
  daily_hours: 2
})

const loading = ref(false)
const streaming = ref(false)
const result = ref('')

const canSubmit = computed(() => {
  return form.value.subject && form.value.start_date && form.value.end_date && form.value.daily_hours > 0
})

// 实时渲染 Markdown
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
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
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
      // 必须累加所有 chunk，包括空白，否则内容会丢失
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

<style scoped>
.page-container {
  max-width: 900px;
  margin: 0 auto;
}

.form-section {
  background: #ffffff;
  border: 1px solid rgba(99, 102, 241, 0.12);
  border-radius: 12px;
  padding: 24px;
  margin-bottom: 24px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.04);
}

.plan-form :deep(.el-form-item__label) {
  color: #94a3b8;
  font-weight: 500;
}

.plan-form :deep(.el-input__wrapper) {
  background: #ffffff;
  box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.2) inset;
  border-radius: 10px;
}

.plan-form :deep(.el-input__inner) {
  color: #1e293b;
}

.plan-form :deep(.el-input__inner::placeholder) {
  color: rgba(148, 163, 184, 0.5);
}

.plan-form :deep(.el-input-number__decrease),
.plan-form :deep(.el-input-number__increase) {
  background: #f1f5f9;
  border-color: rgba(148, 163, 184, 0.2);
  color: #94a3b8;
}

.plan-form :deep(.el-date-editor) {
  background: #ffffff;
  box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.2) inset;
  border-radius: 10px;
}

.plan-form :deep(.el-date-editor .el-input__inner) {
  color: #1e293b;
}

.el-button--primary {
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
  border: none;
  border-radius: 10px;
  font-weight: 500;
}

.btn-icon {
  margin-right: 6px;
}

.result-section {
  background: #ffffff;
  border: 1px solid rgba(99, 102, 241, 0.12);
  border-radius: 12px;
  overflow: hidden;
}

.result-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 18px;
  background: rgba(99, 102, 241, 0.05);
  border-bottom: 1px solid rgba(99, 102, 241, 0.1);
  font-size: 14px;
  font-weight: 600;
  color: #1e293b;
}

.typing-indicator {
  display: flex;
  gap: 4px;
  margin-left: 8px;
}

.dot {
  width: 6px;
  height: 6px;
  background: #6366f1;
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
  color: #475569;
  font-size: 14px;
  line-height: 1.8;
}

:deep(.markdown-body h1),
:deep(.markdown-body h2),
:deep(.markdown-body h3),
:deep(.markdown-body h4),
:deep(.markdown-body h5),
:deep(.markdown-body h6) {
  color: #1e293b;
  margin: 16px 0 10px;
  font-weight: 600;
  border-bottom: 1px solid rgba(99, 102, 241, 0.1);
  padding-bottom: 6px;
}

:deep(.markdown-body h1) { font-size: 22px; }
:deep(.markdown-body h2) { font-size: 18px; }
:deep(.markdown-body h3) { font-size: 16px; }

:deep(.markdown-body p) {
  margin: 8px 0;
  color: #475569;
}

:deep(.markdown-body strong) {
  color: #6366f1;
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
  background: rgba(99, 102, 241, 0.08);
  color: #6366f1;
  padding: 2px 6px;
  border-radius: 4px;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 13px;
}

:deep(.markdown-body pre) {
  background: #f8fafc;
  border: 1px solid rgba(99, 102, 241, 0.1);
  border-radius: 8px;
  padding: 12px 16px;
  overflow-x: auto;
  margin: 10px 0;
}

:deep(.markdown-body pre code) {
  background: transparent;
  padding: 0;
  color: #818cf8;
}

:deep(.markdown-body blockquote) {
  border-left: 3px solid rgba(99, 102, 241, 0.3);
  margin: 10px 0;
  padding: 8px 16px;
  background: rgba(99, 102, 241, 0.03);
  border-radius: 0 8px 8px 0;
}

:deep(.markdown-body blockquote p) {
  margin: 0;
  color: #94a3b8;
}

:deep(.markdown-body hr) {
  border: none;
  border-top: 1px solid rgba(99, 102, 241, 0.1);
  margin: 16px 0;
}

:deep(.markdown-body table) {
  width: 100%;
  border-collapse: collapse;
  margin: 10px 0;
  font-size: 13px;
}

:deep(.markdown-body th) {
  background: rgba(99, 102, 241, 0.06);
  color: #1e293b;
  padding: 8px 12px;
  text-align: left;
  border-bottom: 1px solid rgba(99, 102, 241, 0.15);
}

:deep(.markdown-body td) {
  padding: 8px 12px;
  border-bottom: 1px solid rgba(99, 102, 241, 0.08);
  color: #475569;
}
</style>
