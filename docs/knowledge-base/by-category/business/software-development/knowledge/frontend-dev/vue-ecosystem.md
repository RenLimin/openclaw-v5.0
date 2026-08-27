---
title: Vue 生态体系
description: Vue 3 核心概念、生态系统与最佳实践
source: Vue.js Official Docs; Pinia Docs; Nuxt Docs
version: 1.0
category: business
dimension: software-development
sub_area: vue
type: knowledge
tags: [vue, pinia, nuxt, composition-api, frontend]
xref: [software-development/knowledge/frontend-dev/react-ecosystem.md]
last_reviewed: 2026-08-27
---

# Vue 生态体系

## 核心概念

### 响应式系统

Vue 3 基于 `Proxy` 实现响应式，相比 Vue 2 的 `Object.defineProperty` 有质的提升：

| 特性 | Vue 2 | Vue 3 |
|------|-------|-------|
| 响应式原理 | `Object.defineProperty` | `Proxy` |
| 数组变更检测 | 需要 `Vue.set` | 原生支持 |
| 新增属性检测 | 需要 `Vue.set` | 原生支持 |
| Tree Shaking | 不支持 | 支持（按需引入） |

### Composition API

Vue 3 的核心新特性，解决 Options API 中逻辑分散问题：

```javascript
// Options API（Vue 2 风格）
export default {
  data() { return { count: 0 } },
  computed: { doubled() { return this.count * 2 } },
  methods: { increment() { this.count++ } },
  mounted() { console.log('mounted') }
}

// Composition API（Vue 3 推荐）
import { ref, computed, onMounted } from 'vue'
const count = ref(0)
const doubled = computed(() => count.value * 2)
function increment() { count.value++ }
onMounted(() => console.log('mounted'))
```

### 常用 Composition API

| API | 用途 |
|-----|------|
| `ref()` | 基础类型响应式 |
| `reactive()` | 对象类型响应式 |
| `computed()` | 派生计算属性 |
| `watch()` / `watchEffect()` | 监听变化 |
| `provide()` / `inject()` | 跨层级依赖注入 |
| `defineProps()` / `defineEmits()` | `<script setup>` 类型声明 |

## 状态管理

| 库 | 特点 |
|---|---|
| Pinia（官方推荐） | TypeScript 友好、无 mutations、DevTools 集成 |
| Vuex 4 | 遗留项目使用，Pinia 的前身 |

## 路由

| 库 | 特点 |
|---|---|
| Vue Router v4 | 声明式路由、导航守卫、懒加载 |

## SSR/SSG 框架

| 框架 | 渲染模式 | 适用场景 |
|------|----------|----------|
| Nuxt 3 | SSR/SSG/ISR | 全栈 Vue、SEO 友好 |
| VitePress | SSG | 文档站点 |
| Gridsome | SSG | 内容型站点 |

## 最佳实践

1. **`<script setup>` 优先**：更简洁、更好的 TypeScript 推导
2. **组合式函数（Composables）**：抽离复用逻辑（类似 React Hooks）
3. **组件通信**：Props down / Events up，跨级用 provide/inject
4. **性能**：`v-memo`、`shallowRef`、`defineAsyncComponent`
5. **TypeScript**：`defineProps<{ }>()` 泛型声明 Props 类型
