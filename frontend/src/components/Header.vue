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
  background: rgba(255, 255, 255, 0.9);
  border-bottom: 1px solid rgba(99, 102, 241, 0.08);
  backdrop-filter: blur(10px);
}

.page-title {
  font-size: 20px;
  font-weight: 600;
  color: #1e293b;
  margin: 0;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}
</style>
