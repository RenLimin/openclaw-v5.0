# knowledge-base — 操作手册 (OPERATIONS)

> 版本: v1.0 · 日期: 2026-09-28

## 安装与启动

### 环境依赖

- python3

### 启动命令

```bash
python3 kb_index.py --help
```

### 健康检查

```bash
python3 L2-infra/components/knowledge-base/kb_index.py --validate
```

## 操作指南

### 场景一：验证知识库

```bash
python3 L2-infra/components/knowledge-base/kb_index.py --validate
```

### 场景二：搜索文档

```bash
python3 L2-infra/components/knowledge-base/kb_index.py --query "关键词"
```

### 场景三：查看统计

```bash
python3 L2-infra/components/knowledge-base/kb_index.py --stats
```

## 配置说明

- 解析: Markdown + frontmatter
- 检索: 向量 + 关键词双轨

## 故障排查

### 索引失效

- **症状**: 搜索结果为空
- **原因**: 索引损坏
- **解决**: 重建索引
