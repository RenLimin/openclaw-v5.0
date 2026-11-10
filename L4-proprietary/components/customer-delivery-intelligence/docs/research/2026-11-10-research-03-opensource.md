# 调研 03：GitHub 与 Clawhub 开源方案

> 时间：2026-11-10 ｜ 来源：子代理 2d36ad9f（GitHub API 经代理 127.0.0.1:7897 实测 + Clawhub 实搜）｜ 状态：done

## 一、编排引擎
| 项目 | License | 活跃 | 评价 |
|---|---|---|---|
| Temporal | MIT | ⭐24.3k | 匹配度最高(durable+HITL 原生)，但需常驻 Server，量级小=杀鸡用牛刀；留作升级路径 |
| n8n | Sustainable Use(fair-code) | ⭐210k | Wait/Approval 节点合适，许可证+范式不适 |
| Windmill | AGPL+Apache 双许可+EE 专有 | ⭐18.5k | 许可证分裂，平台过重 |
| Airflow | Apache-2.0 | ⭐47.4k | 无人在环原语，范式错位(批处理调度器) |
| Inngest | SSPLv1 | ⭐6.0k | SSPL 许可红线，生态新 |
| Trigger.dev | Apache-2.0 | ⭐16.7k | v3 durable AI agents+HITL 好，但 TS/React 栈 |

## 二、AI 浏览器自动化
| 项目 | License | 活跃 | 结论 |
|---|---|---|---|
| browser-use | MIT | ⭐120.5k | AI 浏览器代理，用于 UI 漂移兜底；确定性路径不用它(成本+抖动) |
| Playwright | Apache-2.0 | ⭐99.7k | 确定性基石：session 持久化/选择器/下载拦截/截图取证 |
| Playwright MCP | Apache-2.0 | ⭐39.4k | Agent 直控浏览器最佳接缝，本环境已具备 MCP |
| Stagehand | MIT | ⭐26.0k | 部分绑定 Browserbase 云 |
| Skyvern | AGPL-3.0 | ⭐23.4k | AGPL 传染性，平台重，不引入 |
| Steel Browser | Apache-2.0 | ⭐7.9k | 多一层服务，单会话场景 Playwright 够 |

## 三、文档抽取/合同解析
| 项目 | License | 活跃 | 结论 |
|---|---|---|---|
| Docling | MIT | ⭐70.4k | **首选**：PDF/DOCX→结构化(版面+表格→JSON/MD)，IBM 出品，适合扫描件/条款表格 |
| MarkItDown | MIT | ⭐194.7k | Office→MD 快路径，表格保真弱于 docling |
| Unstructured | Apache-2.0 | ⭐15.7k | 本地版依赖多，API 收费 |
| textract | 停滞/云依赖 | ⭐490 | 不推荐 |

## 四、关键词检索
order-to-cash：无通用引擎 ❌；contract acceptance：OpenWorkProof(⭐261)/topplecat 等，概念参考 ❌ 不产品化；delivery acceptance：sulde(⭐92)/SoloDawn(⭐316) 质检门思路参考；RPA document collection：仅 UiPath 示例 ❌。**行业无开箱即用流水线=自建薄 runner 的典型领域**。

## 五、Clawhub 实搜（8 组关键词）
- 回款：@chenqg618/receivable-collection-plan-check-free（逐行复算+原文引用范式 ✅ 借鉴）
- 验收：@golngod/function-acceptance-executor、acceptance-report-gen（✅/⚠️/❌ 三级结论 ✅ 借鉴）
- 合同：@chenqg618/contract-comparison-free、@huhoo/cue-cn-contract-clauses（条款切分/比对方法论 ✅ 借鉴）
- 交付物：@killsnake01/presend-deliverable-inspector（发前体检 ⚠️）
- ONES 专有 skill：0；通用 browser-automation 有，无 OA/ONES 定制 ❌ 抓取层仍需自建
- **结论：Clawhub 无端到端「客户交付/验收/回款」流水线 skill**；4 个高价值组件范式可作薄 runner 内置模板方法论来源

## 六、结论：自建 Python 薄 runner + 复用成熟组件
1. 量级：低频(周数次)、6~8 步、分钟级——Temporal 价值无法兑现，反而引入常驻服务运维面
2. 既有设施契合：仓库已有 job 表异步+前端轮询(进度条铁律)，薄 runner ≈200 行状态机继承该模式
3. 人在环：走现有 Agent 审批流(job 状态+企微通知)，比引擎 Signal/approval 更贴合
4. 许可证：n8n/Inngest/Windmill 有风险；Apache/MIT 组件无负担
5. 真风险点(登录态失效/验证码/UI 变化)引擎也解决不了，靠会话持久化+步骤重试+LLM 兜底
6. 组件选型：抓取=Playwright+Playwright MCP+browser-use 兜底；解析=Docling+MarkItDown；产出=内置 5 类标准模板；编排=薄 runner 步骤「纯函数+状态字典」接口，**预留 Temporal 适配面**作为升级路径

**一句话：现阶段自建薄 runner 正确；Temporal 保留为明确升级路径，不提前引入。**
