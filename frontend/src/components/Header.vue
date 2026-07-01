<template>
  <header class="app-header">
    <h2 class="page-title">{{ pageTitle }}</h2>
    <div class="header-actions">
      <slot />
    </div>
  </header>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()

const titles = {
  '/note': '笔记整理',
  '/plan': '复习计划',
  '/qa': '智能问答',
  '/knowledge': '知识库'
}

const pageTitle = computed(() => titles[route.path] || '')
</script>

<style scoped>
.app-header {
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 28px;
  background: rgba(15, 23, 42, 0.6);
  border-bottom: 1px solid rgba(0, 240, 255, 0.08);
  backdrop-filter: blur(10px);
}

.page-title {
  font-size: 20px;
  font-weight: 600;
  color: #e2e8f0;
  margin: 0;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}
</style>
