# memory-embedding — 操作手册 (OPERATIONS)

> 版本: v1.0 · 日期: 2026-09-28

## 安装与启动

### 环境依赖

- python3
- llama-cpp-provider (GGUF 模型)

### 启动命令

```bash
# 通过 memory_search 工具使用
```

### 健康检查

```bash
# 验证嵌入模型
openclaw memory status
```

## 操作指南

### 场景一：语义搜索

```bash
openclaw memory search "关键词"
```

### 场景二：查看索引状态

```bash
openclaw memory status
```

## 配置说明

- 模型: hf_ggml-org_embeddinggemma-300m-qat-Q8_0.gguf
- 维度: 768
- 索引: 1741 chunks / 177 文件

## 故障排查

### 嵌入失败

- **症状**: 搜索结果为空
- **原因**: 模型文件被移动或损坏
- **解决**: 检查模型文件路径和完整性
