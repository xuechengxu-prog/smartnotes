<template>
  <aside class="sidebar">
    <div class="sidebar-header">
      <el-icon size="28" color="#00f0ff"><Document /></el-icon>
      <span class="brand">SmartNotes</span>
    </div>
    <nav class="sidebar-nav">
      <router-link
        v-for="item in menuItems"
        :key="item.path"
        :to="item.path"
        :class="['nav-item', { active: route.path === item.path }]"
      >
        <el-icon size="18"><component :is="item.icon" /></el-icon>
        <span>{{ item.label }}</span>
      </router-link>
    </nav>
    <div class="sidebar-footer">
      <div class="user-info">
        <el-icon size="18"><User /></el-icon>
        <span class="username">{{ authStore.username }}</span>
      </div>
      <el-button
        type="danger"
        size="small"
        text
        class="logout-btn"
        @click="authStore.logout"
      >
        <el-icon size="16"><SwitchButton /></el-icon>
        退出
      </el-button>
    </div>
  </aside>
</template>

<script setup>
import { useRoute } from 'vue-router'
import { Document, EditPen, Calendar, ChatDotRound, Collection, User, SwitchButton } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth.js'

const route = useRoute()
const authStore = useAuthStore()

const menuItems = [
  { path: '/note', label: '笔记整理', icon: EditPen },
  { path: '/plan', label: '复习计划', icon: Calendar },
  { path: '/qa', label: '智能问答', icon: ChatDotRound },
  { path: '/knowledge', label: '知识库', icon: Collection }
]
</script>

<style scoped>
.sidebar {
  width: 220px;
  height: 100vh;
  background: #0f172a;
  border-right: 1px solid rgba(0, 240, 255, 0.1);
  display: flex;
  flex-direction: column;
  position: fixed;
  left: 0;
  top: 0;
  z-index: 100;
}

.sidebar-header {
  height: 64px;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 20px;
  border-bottom: 1px solid rgba(0, 240, 255, 0.08);
}

.brand {
  font-size: 18px;
  font-weight: 700;
  color: #fff;
  letter-spacing: 1px;
}

.sidebar-nav {
  flex: 1;
  padding: 16px 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-radius: 10px;
  color: rgba(148, 163, 184, 0.9);
  text-decoration: none;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.2s ease;
}

.nav-item:hover {
  background: rgba(0, 240, 255, 0.06);
  color: #e2e8f0;
}

.nav-item.active {
  background: rgba(0, 240, 255, 0.1);
  color: #00f0ff;
  box-shadow: 0 0 15px rgba(0, 240, 255, 0.08);
}

.sidebar-footer {
  padding: 16px;
  border-top: 1px solid rgba(0, 240, 255, 0.08);
}

.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
  color: rgba(148, 163, 184, 0.8);
  font-size: 13px;
  margin-bottom: 8px;
}

.username {
  color: #e2e8f0;
  font-weight: 500;
}

.logout-btn {
  width: 100%;
  justify-content: center;
  color: rgba(239, 68, 68, 0.8);
}

.logout-btn:hover {
  color: #ef4444;
}
</style>
