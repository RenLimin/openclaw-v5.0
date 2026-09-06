# FIN-L4 部署指南

> 本文档描述 FIN-L4 家庭理财管理系统的生产部署方案。
> 目标：**可灵活部署至不同服务器**（Docker 容器 / 裸机 systemd / macOS launchd 三种方式，自动检测）。

---

## 1. 快速开始

```bash
# 一键部署（自动检测 Docker，若无则回退裸机）
./deploy.sh

# 查看部署状态
./deploy.sh --status

# 停止服务
./deploy.sh --stop

# 卸载（保留数据）
./deploy.sh --uninstall
```

**环境变量控制**：

| 变量 | 默认 | 说明 |
|---|---|---|
| `FIN4_PORT` | `8500` | 外部端口 |
| `FIN4_FAMILY_ID` | `default` | 家庭 ID |
| `FIN4_IMPORT` | `0` | 部署后是否导入演示数据 (`1`=是) |
| `FIN4_DB_DIR` | `~/.fin-l4` | 数据目录（裸机部署） |

---

## 2. 部署方式决策（自动检测）

| 服务器条件 | 部署方式 | 说明 |
|---|---|---|
| 已装 Docker 且 daemon 运行 | **容器化** (compose / docker run) | 推荐，dev/prod 一致，一条命令升级 |
| 无 Docker | **裸机 systemd** (Linux) | 开机自启 + 崩溃自愈 |
| macOS | **launchd** | `~/Library/LaunchAgents/com.finl4.web.plist` |

`deploy.sh` 启动时自动检测 `docker info`，可用则走容器化，否则回退裸机。

---

## 3. 容器化部署（Docker）

### 3.1 前置

- Docker ≥ 20.10（支持 compose v2）
- 端口 8500 空闲（可用 `FIN4_PORT` 覆盖）

### 3.2 构建与启动

```bash
# 方式 A: docker compose（推荐）
docker compose up -d --build

# 方式 B: 手动
docker build -t fin-l4:latest .
docker run -d \
    --name fin-l4 \
    --restart unless-stopped \
    -p 8500:8500 \
    -e FIN4_FAMILY_ID=default \
    -v fin4_data:/data \
    fin-l4:latest
```

### 3.3 数据持久化

- 数据卷 `fin4_data` 挂载到容器内 `/data`
- SQLite 数据库位于 `/data/fin_l4.db`
- **升级容器时数据不丢失**（卷独立于容器）

### 3.4 健康检查

```yaml
healthcheck:
  test: ["CMD", "python3", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8500/', timeout=3)"]
  interval: 30s
  timeout: 5s
  retries: 3
  start_period: 10s
```

### 3.5 升级

```bash
docker compose pull && docker compose up -d   # 有 registry 时
docker compose build && docker compose up -d  # 本地构建
```

---

## 4. 裸机部署（Linux systemd）

### 4.1 自动安装

```bash
sudo FIN4_PORT=8500 ./deploy.sh --bare
```

- 创建虚拟环境 `.venv`
- 安装依赖
- 生成 `/etc/systemd/system/fin-l4.service`
- 启用并启动

### 4.2 手动安装（模板参考）

模板：`deploy/fin-l4.service.template`

```bash
sudo cp deploy/fin-l4.service.template /etc/systemd/system/fin-l4.service
# 编辑替换 {{PROJECT_DIR}} {{VENV_PYTHON}} {{PORT}} {{DATA_DIR}} {{FAMILY_ID}}
sudo systemctl daemon-reload
sudo systemctl enable --now fin-l4
```

### 4.3 运维

```bash
sudo systemctl status fin-l4      # 状态
sudo systemctl restart fin-l4     # 重启
sudo journalctl -u fin-l4 -f      # 日志
```

---

## 5. macOS 部署（launchd）

```bash
./deploy.sh --bare   # 自动检测 Darwin 生成 launchd plist
```

服务：`~/Library/LaunchAgents/com.finl4.web.plist`（`RunAtLoad` + `KeepAlive` 自启自愈）

---

## 6. 配置项

完整配置：`.env.example`（复制为 `.env` 生效）

| 配置 | 环境变量 | 默认 | 说明 |
|---|---|---|---|
| 监听地址 | `FIN4_HOST` | `127.0.0.1` | 容器内 `0.0.0.0` |
| 端口 | `FIN4_PORT` | `8500` | |
| 数据目录 | `FIN4_DB_DIR` | `~/.fin-l4` | |
| 家庭 ID | `FIN4_FAMILY_ID` | `default` | |
| 调试 | `FIN4_DEBUG` | `0` | `1` 开启 |
| 外部只读 | `FIN4_EXTERNAL_READONLY` | `1` | 外部系统链接只读 |

> 优先级：**环境变量 > `.env` 文件 > 内置默认**。实现见 `fin_l4/config.py`。

---

## 7. 数据备份与恢复

### 7.1 备份

```bash
# 备份数据库到 ./backups/（保留最近 14 份）
./deploy/backup.sh

# 备份到指定目录
./deploy/backup.sh /path/to/backups
```

> 使用 SQLite `backup` API 在线热备，WAL 模式下一致性好。

### 7.2 恢复

```bash
# 停止服务
./deploy.sh --stop

# 覆盖数据库
cp backups/fin_l4_20260904_220000.db ~/.fin-l4/fin_l4.db

# 启动服务
./deploy.sh --status  # 或对应启动命令
```

### 7.3 Docker 卷备份

```bash
docker run --rm -v fin4_data:/data -v $(pwd)/backups:/backup \
    alpine tar czf /backup/fin4_data_$(date +%Y%m%d).tar.gz -C /data .
```

---

## 8. 初始化数据

```bash
# 部署后导入演示数据（确认功能正常）
FIN4_IMPORT=1 ./deploy.sh

# 单独导入
python3 fin_l4/load_demo_data.py
```

> ⚠️ `load_demo_data.py` 会**清空**当前家庭数据后重建。生产环境已有真实数据时不要运行。

---

## 9. 网络与安全

| 项 | 说明 |
|---|---|
| 监听 | 默认仅 `127.0.0.1`（本地安全） |
| 远程访问 | 需将 `FIN4_HOST=0.0.0.0`，建议前置 Nginx/Caddy TLS |
| 认证 | 当前版本无登录鉴权；远程暴露前需自行加反向代理鉴权 |
| 外部链接 | 只读跳转，不存凭据，不自动同步（`FIN4_EXTERNAL_READONLY=1`） |
| 数据 | 全本地 SQLite，不依赖云 |

---

## 10. 架构验证

- **L4 层定位**：`fin_l4/`（框架 + L3 通用能力继承）+ `fin_l4_pf01/`（L4 实例，家庭专有数据）
- **运行时无关**：不依赖 OpenClaw 运行时，`python3 -m fin_l4.run_web` 独立运行（符合 ADR-012）
- **单端口原则**：全系统仅占用 8500

---

## 11. 部署文件清单

```
finance-engine/
├── deploy.sh                        # 一键部署（自动检测）
├── Dockerfile                       # 生产镜像
├── docker-compose.yml               # compose 编排
├── .env.example                     # 配置示例
├── .dockerignore
├── fin_l4/
│   ├── config.py                    # 配置模块（env/.env/默认）
│   ├── run_web.py                   # 启动入口（配置化）
│   └── requirements.txt
└── deploy/
    ├── backup.sh                    # 数据备份
    └── fin-l4.service.template      # systemd 模板
```
