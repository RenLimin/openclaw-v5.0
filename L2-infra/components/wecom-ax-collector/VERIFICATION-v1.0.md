# VERIFICATION：企业微信 macOS AX 采集器 Phase 1

- 版本：v1.0 ｜ 日期：2026-11-24 ｜ 状态：**通过（含已知边界）**
- 设计：`docs/research/DESIGN-wecom-ax-collector-phase1.md`
- PoC 前置：`docs/research/VERIFICATION-wecom-ax-collection-poc-v1.0.md`
- 组件：`L2-infra/components/wecom-ax-collector/`
- 环境：macOS 27.0.1 (arm64)、企业微信 **5.0.13**（Mac App Store 沙盒版，进程号已隐去）、Python 3.14 / Swift 编译

---

## 一、验收结论

| # | 验收项 | 结果 | 证据 |
|---|---|---|---|
| A1 | 连续运行 ≥5 分钟，无崩溃、内存稳定 | ✅ | 运行 **5 分 04 秒**，RSS 稳定 15~17MB，CPU 0.1%，状态 S，无退出/重启 |
| A2 | 新消息检出且**不重复输出** | ✅ | 轮询序列 `new=15 → 0 → 0 → 0`；累计 JSONL 71 行 **0 重复** |
| A3 | 最小化/后台时采集不中断 | ✅ | 最小化后连续 3 轮 `new=13 → 0 → 0`，无 error |
| A4 | 切换会话后消息区刷新正确 | ⚠️ **通过但有代价** | 内容切换成功（新增 13 条）；但整命令耗时 **5.76s**，远超目标 ≤1s |
| A5 | 输出字段完整 | ✅ | `msg_id / content_hash / session / sender / ts / mentions / media / captured_at` |
| A6 | 杀掉重启后可恢复且不重复旧消息 | ⚠️ **部分** | `.seen_ids.json` 持久化+重启读回已实测（ids/hashes 计数正确）；未做真实 kill -9 演练 |

**总评**：核心链路（只读采集 → 结构化 → 去重 → 落盘）稳定可用；主要短板是 **A4 切换延迟**（点击+渲染等待机制）与 **A6 缺真实崩溃演练**。

---

## 二、关键过程数据

### 2.1 解析质量（同一会话两轮独立采集对比）

| 指标 | 数值 |
|---|---|
| 原始 AX items | 27~46 |
| 还原消息 | 15~19 |
| 时间戳命中 | 10~13 条（唯一归属，无一对多虚报） |
| @提及命中 | 全部含 @ 的消息均提取到（如 `@所有人`、`@张三`） |
| 发送者可见标签 | 稀疏（实测 2~4 条） |
| 媒体占位符 | U+FFFC → `media="unknown"`，不入正文 |
| 噪声隔离 | 「群看板 / 边聊边看工作进展 / 发起人 / 参会人」等卡片字段零泄漏 |

### 2.2 去重指纹稳定性（决定性实验）

固定会话名下连续两次快照，逐条比对指纹：
```
仅快照2: []  仅快照1: []
```
→ 引擎+解析+指纹链路在无新消息时**完全幂等**。这是 A2 的基础。

### 2.3 修复过的真实缺陷（都已回归覆盖）

| 缺陷 | 现象 | 根因 | 修复 |
|---|---|---|---|
| D1 全量误判为新消息 | 第 2 次采集 `new=18` | 指纹含**会话名**，而 `_selected_session()` 会回退到窗口标题「企业微信」，名字一变整批变新 | 指纹改为 `y桶+sender+content`，并加 `content_hash` 二次校验吸收坐标漂移 |
| D2 时间戳漏判为正文 | `11月10日 13:19` 出现在 content | 判定锁死 `x>750`，但实测部分会话时间戳渲染在内容列 x≈348 | 放宽为「消息区内(x≥340) + 全串匹配时间正则」 |
| D3 时间戳一对多 | 同一 `21:24` 错标给 3 条消息 | 最近邻容差 100px 过大且允许重复归属 | 唯一归属贪心匹配（每 ts 最多配一条） |
| D4 媒体占位符入正文 | `￼￼￼` 被当消息 | 未识别 U+FFFC | 新增 media 通道，标注 `unknown` 不入正文 |
| D5 周几时间漏判 | `星期四 20:40` 混入正文 | 正则缺「星期X HH:MM」分支 | 补正则分支（实测 6 个此类节点全在 x≈792） |
| D6 卡片字段污染 | 日历/群看板字段混入 | 内容列上限过宽 | 收紧主列 340≤x≤360，次级列需 w≥80 且 h≥20 |

> D1 是最严重的一个：它让「去重」这个核心承诺失效。已通过「同会话两轮指纹 100% 一致」固化为回归锚点。

---

## 三、边界与限制（如实声明）

### 3.1 拿不到的
- **富媒体本体**：图片 / 文件 / 语音 / 视频内容不可得，仅有文本占位（U+FFFC）或文件名。
- **历史全量**：只能读 UI 已加载内容，回溯靠模拟滚动加载，效率低。
- **实时推送**：轮询模型（默认 3s），非事件驱动。
- **发送消息**：不在本阶段范围。

### 3.2 已知缺口
1. **发送者覆盖率低**：企微只在气泡组开头渲染一次名字（微型标签 x≈346 h=2），AX 树其余位置 `title/description/header` 实测全为 nil。**默认不继承**，故 sender 常为空——宁缺毋错标。可选 `inherit_sender=True` 提升覆盖但引入错标风险。
2. **A4 切换延迟 5.76s**：源于 CGEvent 点击 + 固定 0.7s 渲染等待 + 每次冷启动 Swift 二进制。若需 ≤1s，应改为**常驻引擎进程**（Unix socket / stdin 长连接）避免重复冷启动，并把渲染等待换成「消息区内容变化」轮询判定。
3. **A6 未做真实 kill 演练**：仅验证状态文件读写，未验证异常退出后的半写恢复。
4. **版本耦合**：解析规则基于企微 5.0.13 实测锚点，客户端升级改 AX 结构会导致解析漂移——回归测试 `test_01_parser.py` 即为此设的版本哨兵。

### 3.3 合规与隐私
- 采集内容为**工作对话**，属敏感数据；`data/` 已 `.gitignore` 排除，本轮验证后已清空真实对话。
- 纯只读、不注入、不改客户端 → 封号风险低；轮询间隔 ≥3s 控制频率。
- 前置条件：终端需授予「辅助功能」权限（`--check` 自检可发现）。

---

## 四、回归测试

```
python3 -m pytest L2-infra/components/wecom-ax-collector/tests/
→ 12 passed, 1 skipped（skip 原因：fixture 当时无 U+FFFC 占位符）
```

覆盖：通道分离、时间戳唯一性、sender 不继承、继承模式、@提取、卡片隔离、多行合并、媒体占位、summarize 形状、会话 selected 检测、指纹稳定性、content_hash 吸收漂移。

---

## 五、下一步（Phase 2 候选）

1. **常驻引擎**：消除冷启动，把切换时延从 ~6s 压到 <1s（A4 已取消，只读红线后不再切会话）。
2. **发送者补齐**：评估截图 OCR/VLM 叠加气泡左右判断，或对单人主导会话启用继承。
3. **滚动回溯**：按需加载历史消息（带速率限制）。
4. ~~崩溃演练：kill -9 + 半写 JSONL 恢复~~ → ✅ **已完成，见 §8**。
5. **存储后端**：SQLite / 向量库，供摘要、告警、RAG 消费。

---

## 六、修订（2026-11-24 晚）

### 6.1 只读红线落地（owner 当面明令）
- **引擎物理移除全部 UI 输入能力**：删除 `clickElement()`、`click` 子命令，`chat --session` 不再点击切换（仅作标签透传，读的是当前打开会话）。
- 代码内已无 `CGEvent` / `CGEventSource` / `.post(tap:)` / `AXUIElementSetAttributeValue` / `AXUIElementPerformAction`（仅注释中作为禁令出现）。
- 新增机器门禁 `tests/test_02_readonly_guard.py`（5 个用例，剥注释静态扫描）；全量 **17 passed / 1 skipped**。
- collector `list` 模式语义变更：不再遍历切换，只在「当前人工打开会话命中白名单」时采集，不命中则跳过（E2E 已验：`new=0 skipped=…不在白名单，只读模式不自动切换`）。
- 规则固化：`AGENTS.md`「已登录客户端只读红线」节。

### 6.2 图片通道的更正（推翻 Phase 1 旧结论）
- 旧结论「图片仅 U+FFFC 占位符、本体不可得」**不准确**：占位符在 `AXTextArea`，但消息区同级存在 `AXImage` 元素，其 **`AXImageData` 属性直接带真实 PNG 字节流**。
- 实测提取（一次性探针脚本，纯只读）：可落盘成完整 PNG；2x retina（AX 122pt → 实图 240px）。
- 跨 14 个会话按字节哈希去重：本轮可见大图均为 **UI 资产**（240x240 大表情、微信转发 logo、文件类型图标、成员状态图标），可由 `AXDescription`（如 `icon member online male`、`file pdf emphasized`）+ 尺寸 + 跨会话哈希稳定区分；**本轮样本中未出现真实聊天照片**，故「真实照片分辨率/是否缩略图」尚未验证，待出现时补测。
- 含义：图片识别路线**可能无需截图/OCR 截屏**，直接从 AX 取 PNG 再送 OCR/VLM；但需先完成图片提取的正式只读子命令与真实照片定性。

---

## 七、Phase 2 图片本体提取（2026-11-24，owner 指示执行 (a)）

### 7.1 目标
把「消息区图片」从「只能拿到 U+FFFC 占位符」升级为**可直接取到 PNG 字节**，并
建立「真实内容图 vs UI 资产」的可靠分类，避免把图标/表情污染进下游 OCR/VLM。

### 7.2 引擎新增只读能力
- 子命令 `images [--only-message] [--out DIR] [--with-data]`。
- 原理：消息区 `AXImage` 元素 → `AXImageData`（NSArray 包装逐层下钻）→ `Data` →
  校验 PNG 魔数（`89 50 4E 47`）→ 输出 sha256 / 实际像素尺寸 / desc / embed / 坐标。
- `--out DIR`：落盘文件名 `<sha256前16>_<W>x<H>.png`，已存在则跳过（天然去重）。
- `--only-message`：过滤右侧成员面板（x<1300），实测 31 → 1。
- 严格只读：仅 `AXUIElementCopyAttributeValue`，无点击/键盘/设值；守卫测试通过。

### 7.3 Python 侧：分类 + 关联 + 净化落盘
- `scripts/wecom_images.py`
  - `classify_image(im, session_hits)`：区域 → 跨会话复现 → AXDescription 签名 →
    极小尺寸 四重判定，类别互斥：`side_panel_ui / ui_icon / ui_reused / content`。
  - `associate(images, messages)`：按最近 y **唯一归属**（贪心，容差 120px），
    一张图最多配一条消息。
  - `ImageCatalog`：sha256 × 会话复现记录（JSON 持久化），跨会话≥2 即判 UI 资产。
- `collector.extract_images()` 单向净化：engine 先写 `_staging`，分类后**仅 content**
  提升为正式文件，其余从 staging 删除——磁盘不留 UI 资产。
- 消息记录新增 `images` 字段（仅含 content 图元数据 + `saved_as` 文件名）。

### 7.4 验收证据（本机企微 5.0.13 实测）
| 项 | 结果 |
|---|---|
| 引擎 `images` 冒烟 | ✅ `read_only=True`，31 张（含重复），7 张唯一；二次运行 `written=0`（去重成立） |
| `--only-message` | ✅ 31 → 1（滤掉右侧成员面板 16+ 张 32×32 图标） |
| 图片链路 E2E | ✅ 第1轮 new=16 / images={total:1,content:1}；第2轮 new=0（幂等） |
| 落盘净化 | ✅ 正式目录仅 1 张 content 图（`<sha前16>_240x240.png`），`_staging` 已清空，无 UI 资产残留 |
| 关闭模式回归 | ✅ `images_enabled=false` 时无 `images` 键、不触碰图片目录 |
| 测试 | ✅ 全量 **36 passed**（含 `test_03_images.py` 19 用例；只读守卫 `test_02_readonly_guard.py`） |

### 7.5 尚存的诚实边界（未夸大）
- 本轮样本里被判为 `content` 的候选是 **240×240 / 23093B 的大表情**（跨 14 会话复现过的
  同一字节），**不是聊天照片**；它之所以落到 content，是因为未命中 UI 关键词且非侧栏。
- 因此「真实聊天照片/截图能否取得、分辨率多高、是否缩略图」**仍未验证**——
  需出现真实照片时用本引擎复测，并由 OCR/VLM 定性后再下结论。
- 图片本体提取不依赖截屏权限；但 OCR/VLM 识别属下一步（复用 `ocr-digitalization` /
  `arkcli`），本阶段只做采集与分类。

---

## 八、A6 崩溃安全（2026-11-24，owner 指示补全）

### 8.1 问题
原 `JsonlSink` 是裸追加：`kill -9` / 断电会把最后一行写一半，下游按行解析即崩。
另 `.seen_ids.json` 若被写坏，原实现会静默降级为空集——无告警。

### 8.2 实现（scripts/wecom_collector.py）
- **`JsonlSink.repair(path)`**：静态方法，把残缺尾行截断回最后一个换行；空文件/正常结尾返回 0，
  **只截断、不重写历史内容**。
- **初始化即自愈**：构造时先 repair 已有文件，记录 `repaired_bytes`。
- **写入前尾检**：每次 `emit` 前检查末字节是否为 `\n`，发现残缺立即修复再续写。
- **fsync**：`flush()` + `os.fsync()`，保证记录真落盘后才算成功（默认开启）。
- **CLI `--recover`**：单独修复模式，输出 `beforeB → afterB（丢弃半写尾行 NB）`，不采集。
- **语义声明（at-least-once）**：若在「已写盘、未保存已见集」之间被杀，重启会重复输出该消息；
  采集器取「宁可重复、不可丢失」，由下游按 `msg_id` / `content_hash` 幂等去重。

### 8.3 验收证据（真实 kill -9，非 mock）
| 用例 | 结果 |
|---|---|
| `test_repair_no_file/empty_and_clean` | ✅ 无副作用 |
| `test_repair_truncates_partial_tail` | ✅ 坏尾行剔除、好行不连带删 |
| `test_repair_no_newline_single_line` | ✅ 整行丢弃（无换行=无完整记录） |
| `test_sink_selfheals_before_append` | ✅ 追加前自动清半行，新记录紧跟其后 |
| `test_cli_recover` | ✅ `--recover` rc=0，产物恰为完整行 |
| **`test_real_kill9_leaves_partial_line_then_recovers`** | ✅ **真起子进程、握手式确认半写状态后 SIGKILL**；repair 后历史零丢失、顺序不变，续写干净 |
| `test_seen_store_corrupt_recovers` | ✅ 坏 JSON 降级为空集且不崩 |

- 真实 kill -9 用例连续 3 次运行稳定通过（非时序碰巧）。
- 测试编写中实测到两个反直觉事实并写入设计约束：
  1) 小缓冲区单次 `write()` 基本原子——**必须显式分两段写同一条记录**才能复现半写；
  2) 生成子进程源码曾自身缺闭合引号导致全部行非法 JSON——已修，教训：崩溃演练的 fixture 本身要先能解析。

### 8.4 本轮测试总量
全量 **44 passed**（含只读守卫、图片分类、崩溃安全）。
