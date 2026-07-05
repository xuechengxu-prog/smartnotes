<template>
  <div class="page-container">
    <div class="knowledge-header">
      <h2>知识库</h2>
      <p class="subtitle">添加学习资料，AI 将基于知识库为你解答问题</p>
    </div>

    <!-- 全局知识库选择器 -->
    <div class="collection-selector-card">
      <div class="selector-label">
        <el-icon size="18"><Collection /></el-icon>
        <span>当前知识库</span>
      </div>
      <el-select
        v-model="currentCollection"
        filterable
        placeholder="选择知识库"
        class="collection-selector"
        @change="onCollectionChange"
      >
        <el-option
          v-for="name in collections"
          :key="name"
          :label="name"
          :value="name"
        />
      </el-select>
      <el-button type="primary" plain @click="showCreateDialog = true">
        <el-icon><Plus /></el-icon>
        新建知识库
      </el-button>
      <span class="collection-count">共 {{ collections.length }} 个知识库</span>
    </div>

    <!-- 新建知识库弹窗 -->
    <el-dialog
      v-model="showCreateDialog"
      title="新建知识库"
      width="400px"
      :close-on-click-modal="false"
    >
      <el-form :model="createForm" label-position="top">
        <el-form-item label="知识库名称">
          <el-input
            v-model="createForm.collection_name"
            placeholder="输入知识库名称，如：python_notes"
            @keyup.enter="handleCreateCollection"
          />
          <div class="create-hint">只能包含字母、数字、下划线、中划线</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="handleCreateCollection">
          创建
        </el-button>
      </template>
    </el-dialog>

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
        <el-form-item>
          <el-button type="primary" :loading="adding" :disabled="!addForm.content" @click="handleAdd">
            <el-icon class="btn-icon"><Plus /></el-icon>
            添加到 "{{ currentCollection || 'default' }}"
          </el-button>
        </el-form-item>
      </el-form>

      <el-upload
        class="upload-area"
        drag
        action="/api/knowledge/add/file"
        :headers="uploadHeaders"
        :data="{ collection_name: currentCollection }"
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
            文件将上传到 "{{ currentCollection || 'default' }}" 知识库
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
        <el-select
          v-model="currentCollection"
          placeholder="搜索范围"
          class="search-collection-select"
        >
          <el-option
            v-for="name in collections"
            :key="name"
            :label="name"
            :value="name"
          />
        </el-select>
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
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, UploadFilled, Search, Loading, Collection } from '@element-plus/icons-vue'
import { addKnowledgeText, searchKnowledge, getCollections, createCollection } from '@/api/knowledge'

const savedCollection = localStorage.getItem('knowledge_collection_name') || ''
const currentCollection = ref(savedCollection)
const addForm = ref({
  content: '',
})
const adding = ref(false)
const collections = ref([])

// 新建知识库弹窗
const showCreateDialog = ref(false)
const createForm = ref({ collection_name: '' })
const creating = ref(false)

const searchQuery = ref('')
const searchResults = ref([])
const searching = ref(false)
const hasSearched = ref(false)

const token = localStorage.getItem('token')
const uploadHeaders = computed(() => ({
  Authorization: `Bearer ${token}`,
}))

// 加载用户所有知识库
const loadCollections = async () => {
  try {
    const res = await getCollections()
    collections.value = res.collections || ['default']
    // 如果当前选中的 collection 不在列表中，添加到列表
    const current = addForm.value.collection_name.trim()
    if (current && !collections.value.includes(current)) {
      collections.value.push(current)
    }
  } catch (e) {
    console.error('加载知识库列表失败:', e)
  }
}

const onCollectionChange = (val) => {
  if (val) {
    localStorage.setItem('knowledge_collection_name', val)
  }
}

const handleCreateCollection = async () => {
  const name = createForm.value.collection_name.trim()
  if (!name) {
    ElMessage.warning('请输入知识库名称')
    return
  }
  creating.value = true
  try {
    const res = await createCollection({ collection_name: name })
    ElMessage.success(res.message || '知识库创建成功')
    // 刷新列表并自动选中新创建的知识库
    await loadCollections()
    currentCollection.value = name
    localStorage.setItem('knowledge_collection_name', name)
    showCreateDialog.value = false
    createForm.value.collection_name = ''
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '创建失败')
  } finally {
    creating.value = false
  }
}

const handleAdd = async () => {
  if (!addForm.value.content) return
  // 验证 collection_name 格式
  const name = (currentCollection.value || '').trim()
  if (name) {
    const validNameRegex = /^[a-zA-Z0-9][a-zA-Z0-9_.-]*[a-zA-Z0-9]$/
    if (!validNameRegex.test(name)) {
      ElMessage.error('知识库名称只能包含字母、数字、下划线、中划线，且不能以特殊字符开头或结尾')
      return
    }
  }
  adding.value = true
  try {
    const res = await addKnowledgeText({
      text: addForm.value.content,
      collection_name: name || 'default',
    })
    if (res.duplicate) {
      ElMessage.warning(res.message)
    } else {
      ElMessage.success('知识添加成功')
    }
    localStorage.setItem('knowledge_collection_name', name)
    // 添加成功后刷新 collection 列表
    await loadCollections()
    addForm.value.content = ''
  } catch (e) {
    // 错误提示已在 request.js 拦截器中统一处理，这里不再重复
  } finally {
    adding.value = false
  }
}

const handleUploadSuccess = () => {
  ElMessage.success('文件上传成功')
  loadCollections()
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
    const params = {
      query: searchQuery.value.trim(),
      n_results: 5,
    }
    // 如果当前选中了特定知识库，只搜索该知识库；否则搜索全部
    if (currentCollection.value) {
      params.collection_name = currentCollection.value
    }
    const res = await searchKnowledge(params)
    searchResults.value = res.results || []
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '搜索失败')
    searchResults.value = []
  } finally {
    searching.value = false
  }
}

onMounted(() => {
  loadCollections()
})
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
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.subtitle {
  color: rgba(148, 163, 184, 0.7);
  font-size: 14px;
  margin: 0;
}

.collection-selector-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 20px;
  background: #ffffff;
  border: 1px solid rgba(99, 102, 241, 0.12);
  border-radius: 12px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.04);
  margin-bottom: 24px;
}

.selector-label {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #1e293b;
  font-weight: 500;
  font-size: 15px;
  white-space: nowrap;
}

.collection-selector {
  width: 240px;
}

.collection-selector :deep(.el-input__wrapper) {
  background: #ffffff;
}

.collection-count {
  color: rgba(148, 163, 184, 0.7);
  font-size: 13px;
  margin-left: auto;
}

.create-hint {
  font-size: 12px;
  color: rgba(148, 163, 184, 0.5);
  margin-top: 4px;
}

.add-section {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  margin-bottom: 32px;
}

.add-form :deep(.el-form) {
  background: #ffffff;
  padding: 20px;
  border-radius: 16px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.04);
}

.upload-area :deep(.el-upload-dragger) {
  background: #ffffff;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.04);
}

.add-form :deep(.el-form-item__label) {
  color: #1e293b;
  font-weight: 500;
}

.add-form :deep(.el-textarea__inner),
.add-form :deep(.el-input__inner) {
  background: #ffffff;
  border: 1px solid rgba(148, 163, 184, 0.2);
  color: #1e293b;
}

.add-form :deep(.el-textarea__inner::placeholder),
.add-form :deep(.el-input__inner::placeholder) {
  color: rgba(148, 163, 184, 0.5);
}

.upload-area :deep(.el-upload-dragger) {
  background: #ffffff;
  border: 2px dashed rgba(99, 102, 241, 0.2);
  border-radius: 12px;
}

.upload-area :deep(.el-upload-dragger:hover) {
  border-color: rgba(99, 102, 241, 0.5);
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
  display: flex;
  gap: 12px;
  align-items: center;
}

.search-input {
  flex: 1;
}

.search-collection-select {
  width: 160px;
}

.search-collection-select :deep(.el-input__wrapper) {
  background: #ffffff;
}

.search-input :deep(.el-input__inner) {
  background: #ffffff;
  border: 1px solid rgba(148, 163, 184, 0.2);
  color: #1e293b;
  border-radius: 12px 0 0 12px;
}

.search-input :deep(.el-input-group__append) {
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
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
  background: #ffffff;
  border: 1px solid rgba(99, 102, 241, 0.1);
  border-radius: 12px;
  transition: all 0.3s ease;
}

.result-card:hover {
  border-color: rgba(99, 102, 241, 0.3);
  background: #ffffff;
}

.result-rank {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
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
  color: #1e293b;
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
