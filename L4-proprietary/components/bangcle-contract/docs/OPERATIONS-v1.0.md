# Bangcle 合同管理专家 — 操作手册（OPERATIONS）

| 项 | 值 |
|---|---|
| 文档 | OPERATIONS |
| 版本 | v1.0 |
| 组件编码 | bangcle-contract（CLM-BANGCLE-001） |
| 依据 | PRD / DESIGN-DETAIL / VERIFICATION v1.0 |

> 本期范围：MVP 四步分析闭环（获取→数字化→风险→product-kb 满足度→报告），CLI 驱动。

---

## 1. 环境要求

| 项 | 要求 |
|---|---|
| Python | ≥ 3.10 |
| L3 依赖 | `L3-business/components/contract-management`（同仓库，path 引用） |
| L4 同级依赖 | `L4-proprietary/components/product-kb` + 本地 `data/product_kb.db` |
| L2 依赖 | OCR 组件（扫描件）、持久化 SQLite 约定 |
| 浏览器兜底 | Playwright 1.61 + CDP Chrome（复用 BDMS），`NO_PROXY=*` 连本地 CDP |
| 凭据 | IAM/IMAP/企微等一律从 `~/.openclaw/secrets/` 读取 |

依赖安装（Playwright，仅浏览器兜底需要）：
```bash
python3 -m pip install playwright && python3 -m playwright install chromium
```

---

## 2. 目录结构

```
bangcle-contract/
├── contract_review/
│   ├── ingest.py / digitize.py / parser.py
│   ├── risk.py / kb_match.py / report.py
├── repository/db.py
├── services/oa/{cube.py,browser_fallback.py}
├── cli/contractctl.py
├── data/                     # SQLite、暂存（gitignored）
├── tests/{unit,e2e}
└── docs/
```

---

## 3. 安装与初始化

```bash
cd <repo>
# 1) 确认 product-kb 库存在（缺失则导入价格表重建）
ls L4-proprietary/components/product-kb/data/product_kb.db
#    重建：cd product-kb && ./scripts/init_db.sh && ./scripts/import_price.sh "<价格表.xlsx>"

# 2) 初始化本组件 DB（reviews/kb_matches/audit_logs）
contractctl init-db        # 或 repository 迁移脚本

# 3) 建立 OA 会话（首次 / 会话失效时）
contractctl oa-login       # headless IAM 登录 + 点 OA 卡片换票，写 storage_state
```

---

## 4. 日常操作

```bash
# 上传/本地合同审查
contractctl review --file ./某合同.pdf --source upload

# 从泛微 Cube 拉合同审查（API→浏览器自动兜底）
contractctl review --oa-billid 15134

# 取报告
contractctl report <review_id> --format md
contractctl report <review_id> --format xlsx
```

输出：分步进度（数字化/风险/参照匹配/报告）+ `overall_risk / satisfaction / report_path`。

---

## 5. OA / 凭据运行说明

- OA 为 **泛微 e-cology 9 Cube**，主键 `billid`；会话经 IAM SSO 换票，`storage_state` 有效期约 12h。
- Cookie/state 存本地 `data/`（gitignored），**绝不入库、不打印**。
- Cube REST 失败（403/字段懒加载）自动降级浏览器：CDP Chrome → `iframe#mainFrame` → 取附件。
- 会话过期自动 IAM 重登（headless + IMAP 读验证码），无需人工。

---

## 6. 故障排查

| 现象 | 排查 / 处理 |
|---|---|
| `product_kb.db` 找不到 | 见 §3 重建；kb_match 会标注"未做参照"而非静默通过 |
| OA 返回「登录信息超时 002」 | storage_state 失效，跑 `contractctl oa-login` |
| Cube 接口 403 | 账号无该卡片权限或会话异常；系统自动转浏览器；仍失败报"账号权限" |
| CDP 连不上 9222 | Chrome 未以 remote-debugging 启动；检查 BDMS browser_adapter 启动逻辑；确认 `NO_PROXY=*` |
| IMAP 取到旧验证码 | 登录脚本须"提交前记基准、只取本次新到、倒序最新"（已在 DETAIL 注明） |
| OCR 失败/置信度低 | 该合同标记未数字化，不继续风险扫描；检查 L2 OCR 模型 |
| 大文件无进度 | 确认走 job/分步输出（>10s 必须有进度，进度条铁律） |
| 报告无法条依据 | 法条只能来自 L3 受控规则库；检查 finding.law 是否在 CHECK_RULES |

---

## 7. 安全与合规

- 合同原文全程本地，不发公网模型；语义轨关闭。
- 审计 append-only；幂等键 `billid + event_id`（回写功能本期不开放）。
- 同意/驳回等决策由人做出，本组件只产出解析/比对/建议。

---

## 8. 变更历史

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-10-27 | v1.0 | 初版：MVP 分析闭环运维 + Cube/浏览器兜底排查 |
