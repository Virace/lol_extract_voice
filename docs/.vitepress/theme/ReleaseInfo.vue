<script setup lang="ts">
import { computed } from 'vue'
import { useData } from 'vitepress'
const { frontmatter } = useData()
const updatedOn = computed(() => {
  const date = frontmatter.value.release?.updatedAt || frontmatter.value.release?.publishedAt
  return date ? new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Hong_Kong', year: 'numeric', month: '2-digit', day: '2-digit',
  }).format(new Date(date)) : ''
})
</script>

<template>
  <div v-if="frontmatter.release" class="release-info">
    <span v-if="updatedOn">更新于 {{ updatedOn }}</span>
    <span>Windows x64</span>
  </div>
</template>
