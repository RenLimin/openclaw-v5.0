# maintenance

**定位：** L2 基础设施层 — 运行环境健康巡检与自动修复。

## 功能列表

- Docker daemon 可用性检测
- Colima 虚拟机状态检测
- Colima 自动启动（通过 launchctl 或 `colima start`）
- 健康状态报告输出

## 目录结构

```
maintenance/
├── colima-docker-check.py    # Colima/Docker 健康巡检与自动修复
├── tests/
│   ├── conftest.py
│   └── test_smoke.py
└── DESIGN.md
```

## 使用方式

```bash
python3 colima-docker-check.py
```

返回退出码 0 = 健康，非 0 = 存在问题。

## 依赖

- Python 3
- Docker CLI（`docker info`）
- Colima（macOS 容器运行时）
