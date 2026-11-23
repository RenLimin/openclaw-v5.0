# browser-automation — 验收文档 (VERIFICATION) v2.0

> 版本: v2.0 · 日期: 2026-11-23
> 前置: [VERIFICATION-v1.0.md](./VERIFICATION-v1.0.md)（2026-11-20 记「空占位定位」，本次不覆盖）
> 变更说明: v1.0 记录组件为空占位目录；本次落地启动器资产后组件由占位升级为可执行能力。

## 背景：修的是什么缺口

v1.0 如实记录「本组件不承载代码，真实能力 = registry `browser-isolated-chrome` 条目」。
但该条目只写了 **profile 目录 + CDP 端口约定**，**全仓没有启动器**：

- 专用实例未运行时 `ones_available()` 恒为 `False`，且 `ones_connector` 会因端口错值
  （9222 vs 9333）连不上专用实例后**静默另起浏览器** → 复用失效
- 每轮都要重新摸索 Chrome 启动命令行（`memory/2026-11-20.md:40` 已自记「下轮仍会重复探索」）

即：**约定存在，但「被触发时随时可用」不成立**。v2.0 补的就是这一段。

## 验收标准（Definition of Done）

1. **被触发即可用**：一个幂等命令拉起专用实例；已运行则复用，不重复起进程。
2. **复用登录态**：拉起后 ONES/OA 无需重新登录即可取数（profile 持久化）。
3. **不碰用户 Chrome**：启动/停止按「专用 profile + 专用端口」过滤，`stop` 绝不误伤。
4. **失败可见**：启动超时/无 Chrome/锁冲突均显式失败，不静默降级成另起浏览器。
5. **可审计**：profile / 端口 / 锁 / 进程回收有据可查，登记入 registry。

## 测试范围

- 单元测试 `tests/test_ensure_chrome.py`（10 例，不启真浏览器、不碰用户 Chrome）
- 真实浏览器 E2E（实测记录见下）
- 复用链路实测：`ensure` → `ones_available()` → `HAS_CT`

## 测试用例

| # | 场景 | 输入 | 预期结果 | 实测 |
|---|---|---|---|---|
| TC01 | 幂等复用 | 连续两次 `ensure` | 第二次「复用已运行实例」，不新起进程 | ✅ 首次 1.81s / 二次 0.15s |
| TC02 | 真实启动 | 实例未运行时 `ensure` | CDP 9333 返回 `Browser: Chrome/…` | ✅ Chrome/157.0.8103.79 |
| TC03 | 登录态复用 | 打开 ONES 标签后 `ones_available()` | `True` 且 `localStorage ct = HAS_CT` | ✅ True / HAS_CT |
| TC04 | 不误伤用户 | `stop` 前后统计用户 Chrome 主进程 | 数量不变（1 → 1） | ✅ 1 → 1 |
| TC05 | 端口释放 | `stop` 后 `status` | CDP 不可用、pids 空 | ✅ 可用=False, pids=[] |
| TC06 | 并发安全 | 文件锁串行化 | 同一时刻单实例 | ✅ `oa-live.lock` flock(LOCK_EX) |
| TC07 | 单测覆盖 | `pytest tests/` | 10 passed | ✅ 10 passed in 0.02s |
| TC08 | 复用断点修复 | `ones_connector` 端口 | 9333 对齐 registry，不再静默另起 | ✅ `CDP_URL=…9333`；bdms 16 passed |
| TC09 | 入口可发现 | registry `--query browser` | 命中 ensure_chrome 入口 | ✅ 106 条 entry 路径全真 |
| TC10 | 生命周期闭环 | DESIGN + VERIFICATION + tests | 齐备 | ✅ DESIGN §4 已更新 |

## 实测结果（2026-11-23）

```
启动前: status → CDP 可用=False, pids=[] ; ones_available()=False（预期，实例未起）
ensure : 已启动专用实例 pid=79801, CDP http://127.0.0.1:9333
二次   : 复用已运行实例（0.15s，未新起）
CDP    : GET /json/version → Browser: Chrome/157.0.8103.79
ONES   : 打开标签后 ones_available()=True, localStorage ct=HAS_CT
stop   : 关闭 6 个专用进程；用户 Chrome 主进程 1 → 1（未误伤）；9333 释放
```

## 结论

**通过** —— 隔离 Chrome 从「有约定、无启动器、每轮重复探索」升级为
「一个幂等命令即可用、复用登录态、用后即关」，并消除 bdms 侧 9222 复用断点。

## 遗留（非本次范围）

- 9333 的 launchd 保活未做（按需启动已足够，符合「用后即关」红线）
- `oa_todo_dist.py` 走 `clm-oa-recon` 的 `state.json`（2026-11-20 14:24），与 `oa-live` 双通道并存
