# OPERATIONS-v1.0.md — BDMS 交付月报系统操作手册

## 1. 依赖环境

- Python 3.10+
- 系统：macOS / Linux 均可
- Python 依赖包：
  ```
  pip install pandas openpyxl python-docx fastapi uvicorn
  ```

## 2. 运行方式

### 2.1 CLI 入口

```bash
cd delivery-center

# 生成月报（后台异步）
python -m v2 generate 2026-08

# 生成月报并等待完成
python -m v2 generate 2026-08 --wait

# 查看所有报告
python -m v2 list

# 查看任务状态
python -m v2 status 1

# 查看报告概要
python -m v2 summary 1

# v1 → v2 数据迁移
python -m v2 migrate --dry-run   # 预检
python -m v2 migrate             # 执行

# 启动 Web UI
python -m v2 serve --port 8000
```

### 2.2 Web UI 入口

启动后访问 http://localhost:8000

| 页面 | 路径 | 说明 |
|------|------|------|
| 报告列表 | `/` | 所有月报一览 + 生成入口 |
| 生成报告 | `/generate` | 选择月份提交生成任务 |
| 报告详情 | `/reports/{id}` | 概要 + 预览 + 下载 |

## 3. 数据准备

1. 从 OA 系统导出合同数据 Excel，放到指定目录
2. 从 ONES 系统导出土时数据 Excel，放到指定目录
3. 配置文件中确认文件路径（参考 `v2/config/paths.toml.example`）

## 4. 常见问题排查

### 问题 1：`ImportError: attempted relative import with no known parent package`

**原因**：直接运行 `python main.py` 导致相对导入失败，必须从项目根目录启动。

**解决**：使用 `python -m v2 serve` 启动，不要直接进入 web 目录运行。

### 问题 2：生成时报错 `FileNotFoundError`

**原因**：配置文件中的 OA/ONES 文件路径不正确。

**解决**：检查配置文件中的路径是否正确，确保文件存在。

### 问题 3：Web 无法访问

**原因**：端口被占用，或者启动失败。

**解决**：
1. 检查端口是否被占用：`lsof -i :<port>`
2. 换一个端口启动：`python -m v2 serve --port 8080`

### 问题 4：报告生成后下载失败

**原因**：报告文件目录权限不足。

**解决**：检查报告输出目录权限，确保进程有写入权限。

### 问题 5：迁移后数据不全

**原因**：v1 原始数据路径不正确，或者 dry-run 没执行。

**解决**：
1. 检查 v1 数据路径配置
2. 先执行 `python -m v2 migrate --dry-run` 查看预检结果，确认无误后再执行迁移
