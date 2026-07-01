<template>
  <el-card title="AI生成结果" v-if="result">
    <pre style="white-space: pre-wrap">{{ result }}</pre>
  </el-card>
</template>
<script setup>
defineProps(['result'])
</script>