# credentials

**定位：** L2 基础设施层 — 凭据全生命周期管理（接入、轮换、撤销、审计）。

## 功能列表

- 凭据接入（add：新服务凭据录入）
- 凭据轮换（rotate：定期更新）
- 凭据撤销（revoke：失效处理）
- 凭据审计（audit：全量扫描 + 权限检查）
- 权限一致性检查（check：文件权限 600 校验）
- 凭据泄漏扫描（cred_secrets.py：推送前检查）
- INDEX.md 索引自动维护

## 目录结构

```
credentials/
├── credentials.sh            # 主入口脚本（add/rotate/revoke/audit/check）
├── scan_secrets.sh           # 凭据泄漏扫描 shell 封装
├── cred_scan.py              # 凭据泄漏扫描核心逻辑
├── tests/
│   ├── conftest.py
│   └── test_smoke.py
└── DESIGN.md
```

## 使用方式

```bash
./credentials.sh add <service> <type>     # 接入新凭据
./credentials.sh rotate <service>          # 轮换凭据
./credentials.sh revoke <service>          # 撤销凭据
./credentials.sh audit                     # 审计所有凭据
./credentials.sh check                     # 权限检查
./scan_secrets.sh                          # 凭据泄漏扫描
```

凭据存储在 `~/.openclaw/secrets/`，索引在 `INDEX.md`。

## 依赖

- bash 4+
- Python 3（cred_scan.py）
