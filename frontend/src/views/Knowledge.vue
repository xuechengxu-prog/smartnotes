<template>
  <div class="page-container">
    <div class="knowledge-header">
      <h2>知识库</h2>
      <p class="subtitle">添加学习资料，AI 将基于知识库为你解答问题</p>
    </div>

    <div class="add-section">
      <el-form :model="addForm" label-position="top" class="add-form">
        <el-form-item label="知识内容">
          <el-input
            v-model="addForm.content"
            type="textarea"
            :rows="4"
            placeholder="输入知识内容..."
          />
        </el-form-item>
        <el-form-item label="知识库名称 (collection_name)">
          <el-input v-model="addForm.collection_name" placeholder="输入 collection_name" />
          <div class="collection-hint">只能使用字母、数字、下划线、中划线</div>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="adding" :disabled="!addForm.content || !addForm.collection_name" @click="handleAdd">
            <el-icon class="btn-icon"><Plus /></el-icon>
            添加
          </el-button>
        </el-form-item>
      </el-form>

      <el-upload
        class="upload-area"
        drag
        action="/api/knowledge/add/file"
        :headers="uploadHeaders"
        :data="{ collection_name: addForm.collection_name }"
        :on-success="handleUploadSuccess"
        :on-error="handleUploadError"
        accept=".txt,.md"
      >
        <el-icon class="el-icon--upload"><upload-filled /></el-icon>
        <div class="el-upload__text">
          拖拽文件到此处，或 <em>点击上传</em>
        </div>
        <template #tip>
          <div class="el-upload__tip">
            支持 .txt / .md 格式文件
          </div>
        </template>
      </el-upload>
    </div>

    <div class="search-section">
      <div class="search-box">
        <el-input
          v-model="searchQuery"
          placeholder="输入关键词搜索知识库..."
          class="search-input"
          @keyup.enter="handleSearch"
          clearable
        >
          <template #append>
            <el-button @click="handleSearch">
              <el-icon><Search /></el-icon>
            </el-button>
          </template>
        </el-input>
      </div>

      <div v-if="searching" class="search-loading">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>正在搜索...</span>
      </div>

      <div v-else-if="searchResults.length > 0" class="search-results">
        <div class="results-header">
          <span class="results-count">找到 {{ searchResults.length }} 条相关结果</span>
        </div>
        <div
          v-for="(item, index) in searchResults"
          :key="index"
          class="result-card"
        >
          <div class="result-rank">#{{ index + 1 }}</div>
          <div class="result-content">
            <div class="result-text">{{ item.content }}</div>
            <div class="result-meta">
              <el-tag size="small" type="info" v-if="item.metadata && item.metadata.filename">
                {{ item.metadata.filename }}
              </el-tag>
              <el-tag size="small" type="success" v-if="item.distance !== null">
                相关度: {{ ((1 - item.distance) * 100).toFixed(1) }}%
              </el-tag>
            </div>
          </div>
        </div>
      </div>

      <div v-else-if="hasSearched" class="empty-results">
        <el-icon size="48" color="rgba(148, 163, 184, 0.3)"><Search /></el-icon>
        <p>未找到相关内容</p>
        <span class="hint">尝试使用其他关键词搜索</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, UploadFilled, Search, Loading } from '@element-plus/icons-vue'
import { addKnowledgeText, searchKnowledge } from '@/api/knowledge'

const addForm = ref({
  content: '',
  collection_name: 'default',
})
const adding = ref(false)

const searchQuery = ref('')
const searchResults = ref([])
const searching = ref(false)
const hasSearched = ref(false)

const token = localStorage.getItem('token')
const uploadHeaders = computed(() => ({
  Authorization: `Bearer ${token}`,
}))

const handleAdd = async () => {
  if (!addForm.value.content || !addForm.value.collection_name) return
  // 验证 collection_name 格式
  const name = addForm.value.collection_name.trim()
  const validNameRegex = /^[a-zA-Z0-9][a-zA-Z0-9_.-]*[a-zA-Z0-9]$/
  if (!validNameRegex.test(name)) {
    ElMessage.error('知识库名称只能包含字母、数字、下划线、中划线，且不能以特殊字符开头或结尾')
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

const handleUploadSuccess = () => {
  ElMessage.success('文件上传成功')
}

const handleUploadError = (err) => {
  const detail = err.response?.data?.detail || '上传失败'
  ElMessage.error(detail)
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

<style scoped>
.page-container {
  max-width: 900px;
  margin: 0 auto;
}

.knowledge-header {
  margin-bottom: 24px;
}

.knowledge-header h2 {
  font-size: 24px;
  font-weight: 600;
  margin: 0 0 8px 0;
  background: linear-gradient(135deg, #00f0ff 0%, #7c3aed 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.subtitle {
  color: rgba(148, 163, 184, 0.7);
  font-size: 14px;
  margin: 0;
}

.add-section {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  margin-bottom: 32px;
}

.add-form :deep(.el-form-item__label) {
  color: #e2e8f0;
  font-weight: 500;
}

.add-form :deep(.el-textarea__inner),
.add-form :deep(.el-input__inner) {
  background: rgba(30, 41, 59, 0.6);
  border: 1px solid rgba(148, 163, 184, 0.2);
  color: #e2e8f0;
}

.add-form :deep(.el-textarea__inner::placeholder),
.add-form :deep(.el-input__inner::placeholder) {
  color: rgba(148, 163, 184, 0.5);
}

.collection-hint {
  font-size: 12px;
  color: rgba(148, 163, 184, 0.5);
  margin-top: 4px;
}

.upload-area :deep(.el-upload-dragger) {
  background: rgba(30, 41, 59, 0.4);
  border: 2px dashed rgba(0, 240, 255, 0.2);
  border-radius: 12px;
}

.upload-area :deep(.el-upload-dragger:hover) {
  border-color: rgba(0, 240, 255, 0.5);
}

.upload-area :deep(.el-upload__text) {
  color: rgba(148, 163, 184, 0.7);
}

.upload-area :deep(.el-upload__tip) {
  color: rgba(148, 163, 184, 0.5);
}

.btn-icon {
  margin-right: 6px;
}

.search-section {
  margin-top: 24px;
}

.search-box {
  margin-bottom: 20px;
}

.search-input :deep(.el-input__inner) {
  background: rgba(30, 41, 59, 0.6);
  border: 1px solid rgba(148, 163, 184, 0.2);
  color: #e2e8f0;
  border-radius: 12px 0 0 12px;
}

.search-input :deep(.el-input-group__append) {
  background: linear-gradient(135deg, #00f0ff 0%, #7c3aed 100%);
  border: none;
}

.search-input :deep(.el-input-group__append .el-button) {
  color: white;
  border: none;
  background: transparent;
}

.search-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 40px;
  color: rgba(148, 163, 184, 0.6);
}

.search-results {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.results-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.results-count {
  font-size: 14px;
  color: rgba(148, 163, 184, 0.7);
}

.result-card {
  display: flex;
  gap: 12px;
  padding: 16px;
  background: rgba(30, 41, 59, 0.4);
  border: 1px solid rgba(0, 240, 255, 0.1);
  border-radius: 12px;
  transition: all 0.3s ease;
}

.result-card:hover {
  border-color: rgba(0, 240, 255, 0.3);
  background: rgba(30, 41, 59, 0.6);
}

.result-rank {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: linear-gradient(135deg, #00f0ff 0%, #7c3aed 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 600;
  color: white;
  flex-shrink: 0;
}

.result-content {
  flex: 1;
  min-width: 0;
}

.result-text {
  color: #e2e8f0;
  font-size: 14px;
  line-height: 1.7;
  margin-bottom: 8px;
  white-space: pre-wrap;
  word-wrap: break-word;
}

.result-meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.empty-results {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  gap: 12px;
  color: rgba(148, 163, 184, 0.5);
}

.empty-results p {
  font-size: 16px;
  margin: 0;
}

.empty-results .hint {
  font-size: 13px;
}

@media (max-width: 768px) {
  .add-section {
    grid-template-columns: 1fr;
  }
}
</style>
