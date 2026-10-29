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

> **OA 审查取数顺序**（2026-10-29 起）：① 优先把合同**附件原文**（pdf/docx/扫描件）数字化走全文管线（method=`oa_attachment`，与本地上传同口径）；② 无可用附件时回退卡片摘要 / 主字段拼接文本（method=`oa_cube`）。早期版本只审字段摘要、不审正文的偏差已修复。

---

## 5. OA / 凭据运行说明

- OA 为 **泛微 e-cology 9 Cube**，主键 `billid`；会话经 IAM SSO 换票（IAM 登录后点「OA协同办公平台」应用卡片换票，直导 OA / 跨 context 注入 cookie 均不建立 ecology 会话）。
- **会话有效期：实测约 2 小时 idle 超时**（2026-10-29 实测 13:42 建 / 15:43 失效；非早期侦察估的 12h）。落盘 cookie 全为 session cookie（`expires=-1`：`ecology_JSessionid`/`JSESSIONID`/`__randcode__`），由泛微 e-cology 服务端控制，**客户端不可延长**。
- Cookie/state 存本地 `~/.openclaw/data/clm-oa-recon/state.json`（权限 600，gitignored），**绝不入库、不打印**。
- Cube REST 失败（403/字段懒加载）自动降级浏览器：CDP Chrome → `iframe#mainFrame` → 取附件。
- **会话过期需手动重登**：`contractctl oa-login`（headless IAM + IMAP 读验证码）。注意每次重建**消耗一次真实 IMAP 验证码**，非完全无人值守；命令落盘前会用探针 billid 跑 `checkCardRight`，验证通过才报「✅ 已建立」，绝不假成功。
- **判登录成功看 DOM 不看 URL**：IAM SPA 登录后 URL hash 可能停在 `#/login`，须以页面内容（含「任立民/首页」）为准。
- **E2E 行为**：OA 会话失效时 TC-OA-01~03 自动 **skip 留证**（禁止伪 pass），刷新会话后即恢复真跑。

---

## 6. 故障排查

| 现象 | 排查 / 处理 |
|---|---|
| `product_kb.db` 找不到 | 见 §3 重建；kb_match 会标注"未做参照"而非静默通过 |
| OA 返回「登录信息超时 002」 | 会话约 2h idle 过期（正常现象），跑 `contractctl oa-login` 重建（耗一次 IMAP 验证码）；E2E 此时自动 skip 留证 |
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
- **OA 附件即用即焚**：OA 拉取的合同原文只在系统临时目录（`$TMPDIR/clm_oa_*`，非 git workspace）短暂落盘；数字化读出全文后 `finally` 立即 `rmtree` 删除，审查失败也删，**不长期留存、不入库**。本地上传件仍落 `data/staging/<sha1>`（gitignored）供取证，两条路径策略不同。

---

## 8. 变更历史

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-10-27 | v1.0 | 初版：MVP 分析闭环运维 + Cube/浏览器兜底排查 |
| 2026-10-29 | v1.0 | 更正 OA 会话有效期为实测约 2h idle（原误记 12h）；补换票/落盘/验证码/DOM 判定/E2E skip 等运维事实 |
| 2026-10-29 | v1.0 | OA 审查改用合同附件**原文全文**（原仅审卡片字段摘要）；附件临时目录**即用即焚**（finally rmtree，不留存/不入库）；新增 `contract_review/oa_text.py` + 5 条回归（含临时目录焚毁集成测试），全量 127 passed |
