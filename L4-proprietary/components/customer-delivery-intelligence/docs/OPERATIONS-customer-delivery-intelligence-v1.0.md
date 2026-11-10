# OPERATIONS — customer-delivery-intelligence v1.0

- 对应：PRD v1.0 / DESIGN-OUTLINE v1.0 / DESIGN-DETAIL v1.0
- 状态：**待 Rex 评审** · 2026-11-10

---

## 1. 前置条件

### 1.1 系统要求
- macOS / Linux（生产优先 macOS，与现有 OpenClaw 部署一致）
- Python ≥ 3.11
- Node.js ≥ 20（Playwright 依赖）
- SQLite ≥ 3.35（Python 内置足够）
- 磁盘：≥ 2 GB（原始文件缓存 + 检查点 + 产物）

### 1.2 凭据与权限
- OA 账号（可访问合同台账、验收流程、附件下载）
- ONES 账号（可访问项目、工作项、附件）
- 企微机器人 webhook（人在环通知）
- **凭据存储**：沿用既有 `clm-oa-recon` 机制 + Playwright 持久化 session；不写任何 markdown

### 1.3 网络
- 访问外网（Docling/Playwright 安装）走代理 `http://127.0.0.1:7897`
- 访问 OA / ONES 走内网或直连（按实际配置）

## 2. 安装

### 2.1 克隆与依赖
```bash
cd /workspace/L4-proprietary/components/customer-delivery-intelligence

# Python 依赖
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# 主要依赖：pydantic / docling / markitdown / python-docx / playwright / jsonschema

# Playwright 浏览器
playwright install chromium
```

### 2.2 配置
```bash
cp config.example.yaml config.yaml
# 编辑 config.yaml：
#   - oa.base_url / ones.base_url
#   - browser.session_dir （Playwright 持久化 session 路径）
#   - hitl.wecom_webhook （企微通知）
#   - storage.checkpoint_db （SQLite 路径）
#   - storage.raw_dir / artifacts_dir / golden_dir
```

### 2.3 初始化
```bash
python3 -m runner.main init
# 创建数据库表、目录结构
```

### 2.4 健康检查
```bash
python3 -m runner.main health
# 检查：Python 版本 / SQLite 可写 / Playwright 可启动 / OA session 有效 / ONES session 有效
```

## 3. 启动与使用

### 3.1 命令行启动
```bash
# 启动一个任务（异步，返回 task_id）
python3 -m runner.main start \
  --customer "中国建设银行股份有限公司" \
  --period-start 2026-01-01 \
  --period-end 2026-12-31 \
  --audience internal

# 查看状态
python3 -m runner.main status <task_id>

# 查看进度（每节点状态）
python3 -m runner.main progress <task_id>
```

### 3.2 人在环操作
```bash
# 齐套闸决策
python3 -m runner.main decide <task_id> --gate gate1 --decision approve
# 可选：approve / reject / skip

# 签发闸决策
python3 -m runner.main decide <task_id> --gate gate2 --decision approve
# 可选：approve / revise

# 企微通知中会带 task_id 和决策链接（web UI 或 CLI）
```

### 3.3 断点恢复
```bash
# 中断后从最新检查点恢复
python3 -m runner.main resume <task_id>

# 查看检查点列表
python3 -m runner.main checkpoints <task_id>
```

### 3.4 产物获取
```bash
# 列出产物
python3 -m runner.main artifacts <task_id>

# 导出交付包到指定目录
python3 -m runner.main export <task_id> --output ./output/
```

### 3.5 血缘查询
```bash
# 全文追溯
python3 -m runner.main trace <task_id>

# 指定字段追溯
python3 -m runner.main trace <task_id> --field "contracts[0].payment.schedule[0].amount"
```

## 4. 运维与监控

### 4.1 日志
- 位置：`logs/cdi-<date>.log`
- 级别：DEBUG / INFO / WARNING / ERROR
- 每节点跃迁记录一行 INFO
- 失败记录 ERROR + stacktrace
- 敏感信息（密码、token）自动脱敏

### 4.2 检查点清理
```bash
# 清理 90 天前成功任务、30 天前失败任务
python3 -m runner.main cleanup --days-success 90 --days-failed 30 --dry-run
# 确认无误后去掉 --dry-run
```

### 4.3 原始文件缓存
- 位置：`storage/raw/`
- 按 `task_id/` 分目录
- 成功任务产物归档后，raw 保留 30 天
- 失败任务 raw 保留 7 天

### 4.4 磁盘空间监控
```bash
python3 -m runner.main disk-usage
# 输出：raw / artifacts / checkpoints / logs 各占多少
```

## 5. 故障排查（FAQ）

### 5.1 取数失败 / 登录态失效
- **现象**：N2 失败，错误含 "login required" / "session expired"
- **排查**：
  1. `playwright open --user-data-dir <session_dir>` 手动登录
  2. 确认 OA / ONES 账号未被锁定
  3. 检查网络（内网/VPN）
- **恢复**：修复 session 后 `resume <task_id>` 从 N2 重跑（幂等）

### 5.2 验证码 / UI 变化
- **现象**：N2 超时，截图显示验证码或布局变更
- **排查**：查看截图（`storage/raw/<task_id>/screenshots/`）
- **恢复**：
  1. 短期：人工介入完成验证，更新选择器
  2. 长期：触发 browser-use 兜底（配置 `fallback: "browser-use"`）
  3. 记录 UI 变化，更新 Playwright 脚本

### 5.3 合同解析失败 / schema 校验不通过
- **现象**：N4 部分合同 `review_status=needs_human`
- **排查**：
  1. 查看 `contracts[].extractionErrors`
  2. 检查文件是否为扫描件（需 OCR）
  3. 检查表格格式是否特殊（需 docling 调参）
- **恢复**：人工修正 / 补充后 `resume <task_id>` 从 N4 重跑

### 5.4 数字不一致 / 评估器 BLOCK
- **现象**：N5 `audit.status=BLOCK`
- **排查**：
  1. `audit.checks` 查看具体哪项失败
  2. 常见：付款比例和≠1 / 账龄合计≠未收 / 分摊合计≠合同额
- **恢复**：
  1. 如是抽取错误 → 回 N4 修复
  2. 如是合同本身数据问题 → 标 `data_issue`，人工确认后 skip

### 5.5 人工闸等不到回执
- **现象**：N3/N6 长时间等待
- **排查**：
  1. 确认企微通知发送成功
  2. 确认责任人已查看
- **恢复**：
  1. 催办（重新发送通知）
  2. CLI 手动决策
  3. 不自动超时继续（安全默认）

### 5.6 进程崩溃 / 机器重启
- **现象**：任务中途断了
- **排查**：看日志最后一行
- **恢复**：`resume <task_id>` — 从最新检查点自动继续，不重跑已完成节点

### 5.7 产物乱码 / 字体问题
- **现象**：docx/PPT 打开乱码或字体不对
- **排查**：
  1. 确认目标机安装了微软雅黑/宋体（PPT 字体铁律）
  2. 检查模板字体设置
- **恢复**：改模板字体，重新 `resume <task_id>` 从 N7 重跑

## 6. 安全操作

- ❌ 不要把凭据写进任何配置文件明文（用环境变量或 keychain）
- ❌ 不要把原始合同文件 commit 到 git
- ❌ 不要在公共网络传输未脱敏产物
- ✅ 对外版产物必须走签发闸
- ✅ 定期清理过期 raw 数据

## 7. 升级与回滚

### 7.1 升级
```bash
git pull
pip install -r requirements.txt --upgrade
python3 -m runner.main migrate  # 数据库 schema 迁移
```

### 7.2 回滚
```bash
git checkout <previous-version>
python3 -m runner.main migrate --down
```

### 7.3 兼容性
- 检查点格式：每个版本有 `schema_version`，跨版本自动迁移
- 产物格式：向前兼容（新版本可读取旧产物）
- 黄金基准：按版本冻结，不互相覆盖
