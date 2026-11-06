# DESIGN-DETAIL — Palantir Oncology P4：泛微 OA 审批链读取器 + 外部写连接器 v1.0

> L4 · bangcle-contract · Contract Ontology Bridge **P4** 详细设计（读路径 + 写连接器契约）
> 版本 v1.0 · 状态：**已实现，待 Rex 验收** · 2026-11-06 · Jerry 🦞
> 实现进度：P4.0（会话重建，复用）/ P4.1（审批链读取器）/ P4.3（连接器契约 dry-run）/ P4.4（定时对账只读）已编码；P4.2（真实写端点）冻结，待测试流程单据 + 增量文档 `p4-write-v1.1`
> 上游：`docs/research/PROPOSAL-palantir-p4-oa-writeback-v1.0.md`（立项书）
> 契约基线：`L2-.../ai_kb/ontology/connectors/base.py`、`connectors/saga.py`
> 既有实现：`contract_review/ontology_bridge/connector.py`（P2 本地表写回）

---

## 0. 本版范围与关键事实（2026-11-06 实测）

本详设覆盖 **P4.0 / P4.1 / P4.3 连接器契约 / P4.4 定时对账**。**P4.2 真实写回的端点契约与真机验证**因当前无测试流程单据，本版只定义接口与冻结点，不实现写、不试写。

实测得到的决定性事实：

| 事实 | 结论 | 证据 |
|---|---|---|
| ecology 会话可无人值守重建 | ✅ | `contractctl oa-login` → IAM headless + BDMS `_fetch_iam_captcha`（IMAP `hwhzimap.qiye.163.com:993`）→ OA 卡片 SSO，state 落盘 |
| 审批日志纯 HTTP 重放 | ❌ 不可靠 | `getRequestLogList` 需表单页签发的 4 个签名令牌；裸 POST 被 `LoadRequestLogDataCmd` 拦截 |
| 签名令牌来源 | `loadForm`（form-encoded）→ `signatureSecretKey` / `signatureAttributesStr`；`detailData` → `authStr` / `authSignatureStr`（实测 `detailData` 返 500） | 浏览器全响应捕获 |
| **审批链浏览器路径** | ✅ **稳定，定为读路径** | 真实浏览器打开 `ViewRequest.jsp` 拿到完整 10 条 loglist + base info |

**核心工程决策：P4 读路径走真实浏览器驱动**（满足"E2E 模拟真实人工操作"铁律），不逆向 ecology 签名链；写路径保持冻结，等测试单据。

---

## 1. 模块划分

```
services/oa/
  cube.py                     # 既有：合同卡片只读（GET/JSON），本版不改其读路径
  browser_fallback.py         # 既有：refresh_oa_session（会话重建）
  approval_log.py             # 【新增】审批链读取器（浏览器驱动 + 归一化）
contract_review/ontology_bridge/
  connector.py                # 既有：ContractWritebackConnector（本地表，可逆）
  oa_connector.py             # 【新增】OaWritebackConnector（外部写，不可补偿）
  reconcile.py                # 【新增】定时对账：OA 当前态 ↔ 本地决策记录
tests/
  test_oa_approval_log.py     # 【新增】读取器单测（黄金夹具重放，不触网）
  fixtures/oa_log_882663.json # 【新增】脱敏黄金夹具（源自 /tmp/oa_log_capture.json）
```

分层边界：审批链的**读取与归一化**属 L4（对接具体 OA DOM/XHR）；L2 只提供 Saga/连接器抽象，不沉淀任何 OA 字段映射；L3 审批状态机仍是 next_status 裁决单一来源。

---

## 2. P4.0 会话重建（已验证，固化复用）

复用 `browser_fallback.refresh_oa_session()`，不重写：

- 输入：无（凭据从 `~/.openclaw/secrets/iam.email_username` / `iam.email_password` 读取，权限 600）。
- 流程：IAM headless 登录 → `_fetch_iam_captcha()`（IMAP 轮询 6 位码）→ 点 OA 卡片 SSO 换票 → `storage_state` 落 `~/.openclaw/data/clm-oa-recon/state.json` → 探针 billid `15134` 只读校验。
- 输出信封：
  ```json
  {"ok": true, "state_path": "~/.openclaw/data/clm-oa-recon/state.json", "probe_billid": "15134"}
  ```
- 失败：IMAP 超时 / 探针失败 → `{"ok": false, "stage": "iam_login|captcha|sso|probe", "error": "..."}`，不抛裸异常给上层。

---

## 3. P4.1 审批链读取器（核心新增）

### 3.1 对外接口

```python
# services/oa/approval_log.py
class ApprovalLogReader:
    def __init__(self, state_path: str | None = None, *,
                 headless: bool = True, timeout_ms: int = 60000) -> None: ...

    def read_approval_chain(self, requestid: str | int) -> "ApprovalChain":
        """真实浏览器打开 ViewRequest.jsp → 点「流转意见」→ 拦截 XHR 归一化。

        会话失效时自动触发一次 refresh_oa_session 后重试一次；
        仍失败抛 ApprovalLogUnavailable（上层据此降级 unknown，不伪造）。
        """
```

### 3.2 浏览器捕获契约（已实测）

- 页面：`https://oa.bangcle.com/workflow/request/ViewRequest.jsp?requestid=<id>`
- 监听响应：
  - `…/getRequestLogBaseInfo` → `ApprovalChain.base`
  - `…/getRequestLogList` → 取 `loglist` 非空的那条（该页可能发多次）
- 交互：加载后点「流转意见」触发懒加载（实测不点只拿 base）。
- 上下文：`new_context(storage_state=<state_path>)`，`headless` 默认 True。

### 3.3 归一化数据模型

```python
@dataclass
class ApprovalEntry:
    node: str          # log_nodename，如「商务」「分管总监」
    operator: str      # displayname
    operator_id: str   # displayid（OA 工号，身份映射主键）
    dept: str          # displaydepname
    action: str        # operationname：提交/批准/退回/抄送/批注…
    opinion: str       # log_remarkHtml 去标签、压缩空白后的纯文本
    date: str          # log_operatedate
    time: str          # log_operatetime
    receivers: str     # receiveUser
    log_id: str        # logid

@dataclass
class ApprovalChain:
    requestid: str
    workflowid: str
    tx_status: str          # base.txStatus（1=流程在途/已办语义，按 OA 字典）
    creator_node_id: str    # base.creatorNodeId
    viewer_user_id: str     # base.userId
    entries: list[ApprovalEntry]   # 按时间倒序（OA 原始顺序）

    def current_node(self) -> ApprovalEntry | None: ...
    def to_dict(self) -> dict: ...
```

`opinion` 归一化规则（固定，供黄金基准）：
`re.sub(r"\s+"," ", re.sub(r"<[^>]+>","", html)).strip()`，`&nbsp;` 经 HTML 转义处理。

### 3.4 黄金夹具（脱敏）

源：`/tmp/oa_log_capture.json`（requestid 882663，base + 10 条原始日志）。
落仓：`tests/fixtures/oa_log_882663.json`，**只保留归一化所需字段**；不保留任何 cookie/token/签名（原始捕获里的 `signatureAttributesStr` 等不进夹具）。
测试：`ApprovalLogReader` 的**归一化函数**接收夹具原始结构 → 断言 10 条、关键字段（如「阚志刚/批准/同意」「王仙仙/退回/请修改产品版本」）。浏览器 I/O 部分用注入的假响应对象测，不触网。

---

## 4. P4.3 OaWritebackConnector（外部写，不可补偿）

### 4.1 类契约

```python
# contract_review/ontology_bridge/oa_connector.py
class OaWritebackConnector(WritebackConnector):
    name = "oa_writeback"

    def __init__(self, *, step_name: str = "oa_writeback",
                 dry_run: bool = True) -> None: ...

    def apply(self, ctx: SagaContext) -> None:
        """P4.2 未完成前：dry_run=True → 只落审计、不发写请求。
        dry_run=False（测试单据 + Rex 二次授权后）→ 调真实 OA 写端点。
        """

    def compensate(self, ctx: SagaContext) -> None:
        """恒抛 CompensationUnavailable——OA 外部写不可物理回滚。"""
```

### 4.2 "外部写不可补偿"语义（Rex 已拍板，核心是不影响 OA 正常流程）

- `apply` 成功后 OA 流程已流转，**任何补偿都不得反向改 OA**。
- `compensate` **恒抛** `CompensationUnavailable`；`SagaOrchestrator` 捕获后：
  - 该步进 `report.compensation_unavailable`；
  - 置 `report.reconciliation_required = True`；
  - 生成**人工冲销工单**记录（动作/单据/时间/原因），本地审计 append-only；
  - Proposal 结果标 `result = "externally_committed"`，**绝不宣称"已回滚"**。
- 更早的、可逆的已成功步骤（如本地表写回）仍由编排器正常逆序补偿——OA 步自身不回滚，不阻断其它步补偿。

### 4.3 写安全护栏（P4.2 落地时强制，本版先冻结接口）

- **preflight**：写前查会话 + 当前节点；会话超时 → 提案 failed，**不重试写**（防重复提交）。
- **幂等键**：写前查当前节点，已流转则跳过；同 idempotency_key 重放不产生第二次 OA 动作。
- **单据白名单**：仅 Rex 指定的测试 requestid 可写；真实在审合同 id 命中即拒。
- 写端点 URL / CSRF / nonce / body 契约：**P4.2 抓包后补本节，当前留空，禁止臆造**。

---

## 5. P4.4 定时对账（按 Rex 拍板，不走 webhook）

理由：无开放平台应用凭证，webhook 无注册端点；定时轮询只读端点即可发现偏差，且全部为只读、无外部副作用。

```python
# contract_review/ontology_bridge/reconcile.py
@dataclass
class ReconcileDiff:
    requestid: str
    local_state: str      # 本地决策记录的预期态
    oa_state: str         # ApprovalChain 反映的 OA 当前态
    kind: str             # in_sync | oa_ahead | local_ahead | oa_unknown

def reconcile(requestids: list[str]) -> list[ReconcileDiff]: ...
```

- 频率：由 automations / cron 编排（默认每 30 分钟，具体在 OPERATIONS 定），只读。
- `oa_unknown`（会话失效/端点变更）→ 报告但不自动重建、不写；连续 N 次偏差才通知 Rex，避免噪音。
- 对账只报告与落审计，**不自动触发写回**（写永远走提案 + 授权）。

---

## 6. 错误与降级

| 情形 | 行为 |
|---|---|
| 会话超时 | 读取器自动重建一次重试；仍败 → `ApprovalLogUnavailable`，审批态降级 `unknown` |
| loglist 被拦截 / 为空 | 不伪造审批链，抛 `ApprovalLogUnavailable`，附 requestid |
| 写端点缺失（本版） | `dry_run` 只落审计；非 dry_run 直接拒绝并提示 P4.2 未闭合 |
| OA 补偿被请求 | 恒 `CompensationUnavailable` + 人工工单，不回滚 OA |
| 对账偏差 | 只报告，不自动写 |

新增异常统一放各模块，不吞异常、不静默。

---

## 7. 验收标准（DETAIL 通过后、编码完成时）

1. `ApprovalLogReader` 归一化黄金夹具：10 条，节点/处理人/动作/意见与实测一致；
2. 浏览器 I/O 用假响应单测覆盖（base + loglist + 点击触发），全程不触网；
3. `OaWritebackConnector.compensate` 恒抛 `CompensationUnavailable`，dry-run apply 只落审计；
4. `reconcile` 对 `in_sync / oa_ahead / local_ahead / oa_unknown` 四态判定正确，且不产生任何写；
5. L4 `bangcle-contract` 全量测试回归通过，既有 `ContractWritebackConnector`（本地表可逆）行为不变；
6. 不新增第三方依赖（Playwright 已是既有依赖）；无凭据/令牌/验证码写入任何文件或 markdown。

**明确不在本版验收：** P4.2 真实写回端点与真机流转——待 Rex 提供测试流程单据并二次授权后，以增量文档 `…-p4-write-v1.1` 补 §4.3 并实施。

---

## 8. 待 Rex 拍板

1. 读路径锁定"真实浏览器驱动"、放弃纯 HTTP 签名链逆向 —— 是否认可；
2. `OaWritebackConnector.compensate` 恒抛 + 人工冲销工单 + `externally_committed` 语义 —— 是否认可；
3. P4.4 定时对账（默认 30 分钟、只读、不自动写）—— 是否认可；
4. 本详设通过后，即按 §7 编码（读路径 + 连接器契约 + 对账），P4.2 留待测试单据。
