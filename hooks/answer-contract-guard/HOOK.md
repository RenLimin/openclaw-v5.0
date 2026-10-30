---
name: answer-contract-guard
description: "Audit outbound messages that carry answer-contract evidence markers (ADR-035 P1/P2) for mandatory P1 signals; observation-only, never cancels delivery"
metadata:
  { "openclaw": { "events": ["message:sent"] } }
---

# Answer Contract Guard

Runtime delivery guard for the ADR-035 answer-contract system (P1/P2/P3).

- `message:sent` → if the outbound content carries any evidence marker
  (`【已验证` / `【推断` / `【缺失`), audit mandatory P1 signals and append one
  audit line to `~/.openclaw/state/answer-contract-audit.log`.
- Checks: source timestamp on `【已验证` (P1 §2), evidence grade present,
  `【推断` traceable (P1 §2), degradation flagged when non-real-time data is
  referenced (P1 §3), trace chain present (P1 §4.5).
- **Observation-only by design**: never cancels or rewrites delivery. Hard gates
  remain the pre-commit golden suite and `check_answer_contract.py`; this hook
  audits what actually leaves the agent, closing the loop.
- Ordinary chat never uses the P1 marker vocabulary, so non-contract messages
  are skipped instantly.

State file: `~/.openclaw/state/answer-contract-audit.log` (append-only).
