# OFC-001 Office 合同审批模块 OPERATIONS v1.0

## 1. 依赖环境

### 1.1 Python 依赖

- Python >= 3.10
- `python-docx` >= 1.1.0
- `fastapi` >= 0.100.0
- `pytest` >= 7.0 (仅测试需要)
- `uvicorn` >= 0.23.2 (运行 Web API 需要)

### 1.2 其他依赖

- 内置 SQLite（Python 标准库已包含，不需要额外安装）
- 依赖 `L3-business/skills/contract-approval` 模块（同项目已存在，不需要额外安装）

### 1.2 安装依赖

```bash
cd L4-proprietary/components/office-contract
pip install -r requirements.txt
```

## 2. 运行方式

### 2.1 初始化数据库

```bash
cd L4-proprietary/components/office-contract
python3 -m cli.contractctl init
```

### 2.2 CLI 使用

创建合同：
```bash
python3 -m cli.contractctl create \
  --title "技术服务合同-XX项目" \
  --party-b "客户公司名称" \
  --amount 250000 \
  --type tech_service \
  --effective-date 2026-09-01 \
  --expiry-date 2027-08-31
```

提交审批：
```bash
python3 -m cli.contractctl submit --id 1
```

审批操作：
```bash
python3 -m cli.contractctl approve --id 1 --approver "张三" --role "销售经理" --comment "同意"
python3 -m cli.contractctl reject --id 1 --approver "张三" --role "销售经理" --reason "金额需要调整"
```

风险扫描：
```bash
python3 -m cli.contractctl risk-scan --id 1
```

生成合同文档：
```bash
python3 -m cli.contractctl generate --id 1
```
生成后的文档保存在 `outputs/` 目录。

签署和归档：
```bash
python3 -m cli.contractctl sign --id 1
python3 -m cli.contractctl archive --id 1
```

查看合同列表和详情：
```bash
python3 -m cli.contractctl list [--status approved] [--page 1]
python3 -m cli.contractctl show --id 1
```

### 2.3 运行 Web API

```bash
cd L4-proprietary/components/office-contract
uvicorn src.office_contract.web.main:app --host 0.0.0.0 --port 8822
```

服务启动后，可访问 `http://localhost:8822/docs` 查看 API 文档并在线调试。

## 3. 常见问题排查

### Q1: 运行 CLI 时报 `ModuleNotFoundError`

**原因**：Python 路径没有包含项目根目录。

**解决**：在项目根目录执行，或手动添加：
```bash
cd /Users/bangcle/.openclaw/workspace
export PYTHONPATH=.
cd L4-proprietary/components/office-contract
python3 -m cli.contractctl [command]
```

### Q2: 报错 `Error: database table already exists`

**原因**：数据库已经初始化过了，不需要重复初始化。

**解决**：如果需要重置数据库，请先删除现有数据库文件：
```bash
rm data/office_contract.db
python3 -m cli.contractctl init
```

### Q3: Web API 启动失败 `Address already in use`

**原因**：端口 8822 被占用。

**解决**：换一个端口启动：
```bash
uvicorn src.office_contract.web.main:app --host 0.0.0.0 --port 8823
```

### Q4: 风险扫描时报模块找不到

**原因**：`L3-business/skills/contract-approval` 不存在或路径不对。

**解决**：确认项目结构正确，该模块应该位于 `L3-business/skills/contract-approval/`。

### Q5: 生成文档后找不到输出文件

**原因**：输出目录不存在，或者权限不足。

**解决**：
```bash
cd L4-proprietary/components/office-contract
mkdir -p outputs
chmod u+rw outputs
```
重新生成即可。

### Q6: 测试执行失败部分用例

**解决**：检查是否所有依赖都正确安装，版本满足要求，检查 L3 模块路径正确。如果还是失败，可以执行：
```bash
git status
git pull
```
确保代码是最新版本。

