# Auth Gateway — 认证网关组件

> **状态**: 📐 骨架阶段 (v0.1)
> **所属层**: L0 Gateway
> **依赖**: 无（L0 层最前置组件，L0 内部被 channel-router 调用）

---

## 1. 职责

L0 层的**安全第一道防线**。

- 身份认证：验证消息发送者身份（签名校验 / Token 校验 / API Key）
- 接入授权：粗粒度的通道级 / 用户级权限控制（细粒度工具权限在 L1 tool-policy）
- 速率限制：按用户 / 按通道 / 全局的请求限流
- 审计日志：认证结果全量记录（成功/失败/原因）

---

## 2. 核心接口

### 2.1 AuthProvider (ABC)

```python
class AuthProvider(ABC):
    name: str
    def verify(self, request: AuthRequest) -> AuthResult: ...
    def issue(self, identity: Identity) -> str: ...       # 签发 Token（可选）
    def revoke(self, token: str) -> bool: ...             # 吊销（可选）
    def supports(self, auth_type: str) -> bool: ...
```

### 2.2 RateLimiter (ABC)

```python
class RateLimiter(ABC):
    def allow(self, key: str, tokens: int = 1) -> bool: ...
    def remaining(self, key: str) -> int: ...
    def reset_at(self, key: str) -> datetime: ...
```

### 2.3 Identity (dataclass)

| 字段 | 类型 | 说明 |
|---|---|---|
| `user_id` | str | 用户唯一标识 |
| `channel` | str | 来源通道 |
| `roles` | list[str] | 角色列表 |
| `permissions` | list[str] | 权限标识列表（粗粒度） |
| `authenticated_at` | datetime | 认证时间 |
| `expires_at` | datetime \| None | 过期时间 |

---

## 3. 状态

| 模块 | 状态 | 说明 |
|---|---|---|
| 身份模型 | ✅ 骨架 | `models.py` 定义 Identity / AuthRequest / AuthResult |
| AuthProvider ABC | ✅ 骨架 | `auth_provider.py` 定义认证提供者抽象基类 |
| RateLimiter ABC | ✅ 骨架 | `auth_provider.py` 内定义 |
| 签名认证实现 | 📋 待开发 | HMAC / RSA 签名验证 |
| Token 认证实现 | 📋 待开发 | JWT / Bearer Token |
| 令牌桶限流实现 | 📋 待开发 | TokenBucketRateLimiter |

---

## 4. 测试

| 测试文件 | 用例数 | 覆盖 |
|---|---|---|
| `test_auth_skeleton.py` | 11 | ABC 契约 / 身份模型 / 认证结果 / 限流接口 |

运行：`pytest components/auth-gateway/tests/`
