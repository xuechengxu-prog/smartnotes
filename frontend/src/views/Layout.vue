<template>
  <div class="layout">
    <Sidebar />
    <div class="main">
      <Header />
      <div class="content">
        <router-view />
      </div>
    </div>
  </div>
</template>

<script setup>
import Sidebar from '@/components/Sidebar.vue'
import Header from '@/components/Header.vue'
</script>

<style scoped>
.layout {
  display: flex;
  min-height: 100vh;
  background: #f0f4f8;
}

.main {
  flex: 1;
  margin-left: 220px;
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}

.content {
  flex: 1;
  padding: 24px 28px;
  overflow-y: auto;
}

/* QA 页面不需要 padding，让 QA.vue 自己管理布局 */
.content:has(.page-container) {
  padding: 0;
  overflow: hidden;
}
</style>
