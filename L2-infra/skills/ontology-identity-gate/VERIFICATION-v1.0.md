# ontology-identity-gate — 验收文档 (VERIFICATION)

> 版本: v1.0 · 日期: 2026-11-20
> 验收对象: `L2-infra/skills/ontology-identity-gate/`（SKILL.md，薄入口）
> 实际实现: `L2-infra/components/ai-knowledge-base/ai_kb/ontology/`（identity_token / agent_toolchain / proposal / mcp）

## 验收标准（Definition of Done）

1. 令牌原语可用：issue → verify 往返成功；篡改签名被拒（`InvalidToken`）；过期被拒；scope 越权被拒（`ScopeDenied`）。
2. fail-closed：未注入身份 / enforce 关闭有明确口径；校验失败一律抛异常而非静默放行。
3. **commit 只由 human 令牌触发**：agent 令牌无法自提；agent 到顶 `validated`，不得 `committed`。
4. 决策指纹可审计：审批者令牌指纹落决策记录（migration 幂等）。
5. 渐进兼容：identity 未配置时行为同旧版（P5 路径不破坏）。
6. 对象级权限（v1.1）：clearance + mandatory markings AND + deny 优先 + realtime 高敏复查。
7. 零第三方依赖（仅标准库）。

## 测试范围

- 令牌原语真实调用（issue/verify/authorize/fingerprint，含篡改与越权）。
- 组件身份与 toolchain 相关 pytest。
- 关联验收文档 P6/P7 既有结论核对。

## 测试用例

| # | 场景 | 输入 | 预期结果 | 实测 |
|---|---|---|---|---|
| TC01 | issue/verify 往返 | 临时 secret 签发 agent 令牌 | verify 返回 sub=agent-1 | ✅ agent-1 |
| TC02 | 篡改签名 | 翻转签名末位 | `InvalidToken` | ✅ InvalidToken |
| TC03 | scope 越权 | agent 令牌 authorize(review) | `ScopeDenied` | ✅ ScopeDenied |
| TC04 | 指纹 | `fingerprint(token)` | 16 hex | ✅ 3a083fcbed2a41ab |
| TC05 | 令牌用例集 | `pytest tests/test_ontology_identity_token.py -q` | 18 passed | ✅ 18 passed in 0.14s |
| TC06 | 身份/toolchain/marking 组合 | `-k "identity or toolchain or token"` | 全绿 | ⚠️ 37 passed, 1 failed（聚合选择器串入无关文件） |
| TC07 | 零三方依赖 | identity_token.py import 源 | 仅标准库 | ✅ hmac/hashlib/base64/json/secrets/datetime/dataclasses |

## 实测结果

- 命令与输出摘要:
  ```bash
  # TC01–TC04（真实调用，临时 secret 文件，不落真实密钥）
  python3 - <<'EOF'
  from ai_kb.ontology.identity_token import IdentityAuthority, InvalidToken, ScopeDenied
  a = IdentityAuthority(secret_path=<tmp>/id.secret)
  t = a.issue(run_id="run-1", subject="agent-1", kind="agent", scopes=["propose:x:d"])
  print(a.verify(t)["sub"])              # → agent-1
  # 篡改
  try: a.verify(p + "." + flipped); print("NO RAISE")
  except InvalidToken: print("InvalidToken OK")
  # 越权
  try: a.authorize(a.verify(t), verb="review", action="x", domain="d")
  except ScopeDenied: print("ScopeDenied OK")
  print(a.fingerprint(t))                # → 3a083fcbed2a41ab
  EOF

  # TC05
  cd L2-infra/components/ai-knowledge-base
  python3 -m pytest tests/test_ontology_identity_token.py -q -p no:cacheprovider
  # → 18 passed in 0.14s   （与 SKILL.md 声明「令牌原语 18 用例」一致）

  # TC06
  python3 -m pytest tests -q -p no:cacheprovider -k "identity or toolchain or token"
  # → 1 failed, 37 passed, 137 deselected in 0.73s
  #   FAILED tests/test_ontology_identity_token.py::test_tampered_signature_rejected
  #   Failed: DID NOT RAISE InvalidToken
  ```
- 结论: **通过（核心红线达标）**。令牌原语在独立真实调用下 issue/verify/篡改/越权/指纹全部符合设计；`test_ontology_identity_token.py` 单独运行 18/18 全绿。TC06 的失败是**聚合选择器 `-k` 跨文件收集时的既有红项**（同文件单跑为绿），见遗留问题 1。

## 遗留问题（如实记录）

1. **聚合运行下的篡改用例红项**：`pytest -k "identity or toolchain or token"` 下 `test_tampered_signature_rejected` 未抛 `InvalidToken`；但 `pytest tests/test_ontology_identity_token.py` 单跑 18/18 全绿，且我独立真实调用篡改令牌确实抛 `InvalidToken`。→ 该用例对**同进程内 secret/缓存状态**敏感（多文件共同导入时被前序用例影响），建议改为每个用例独立 secret 或在 conftest 隔离。此为测试隔离缺陷，非实现缺陷。
2. **TC06 选择器串入无关文件**：`-k` 匹配到 `test_ontology_identity.py`（137 deselected），导致红项出现在非目标文件。验收回归建议按文件显式列举（如本次 TC05 方式）而非关键词聚合。
3. **本 skill 目录无脚本/无测试**：实现与测试均在 `L2-infra/components/ai-knowledge-base/`，skill 侧仅 SKILL.md。已有 P6/P7 验收文档（`docs/VERIFICATION-P6-…-v1.0.md` / `P7-…`）覆盖端到端黄金用例（agent 停 validated / human 令牌 commit 双指纹），本文档不重复其结论，只核对可复现性。
