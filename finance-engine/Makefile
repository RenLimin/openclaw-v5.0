# FIN-L4 家庭理财管理系统 — 统一命令入口
# 使用 make <tab> 查看所有可用命令

.PHONY: help install run test test-verbose build up down logs backup status stop clean docs version

.DEFAULT_GOAL := help

help: ## 显示所有可用命令
	@awk 'BEGIN {FS = ":.*##"; printf "\n\033[1mFIN-L4 可用命令:\033[0m\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

install: ## 一键部署（自动检测 Docker / 裸机）
	@./scripts/setup.sh

run: ## 本地开发运行
	@python3 -m fin_l4.run_web

test: ## 运行测试
	@python3 -m pytest tests/test_fin_l4* -q

test-verbose: ## 详细测试输出
	@python3 -m pytest tests/test_fin_l4* -v

build: ## 构建 Docker 镜像
	@docker build -t fin-l4:latest .

up: ## docker compose 启动服务
	@docker compose up -d --build

down: ## docker compose 停止服务
	@docker compose down

logs: ## 查看服务日志
	@docker compose logs -f

backup: ## 数据备份
	@./deploy/backup.sh

status: ## 查看部署状态
	@./deploy.sh --status

stop: ## 停止服务
	@./deploy.sh --stop

clean: ## 清理缓存文件
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "\u6e05\u7406\u5b8c\u6210"

docs: ## 列出所有文档路径
	@echo "\U0001f4da \u6587\u6863\u6e05\u5355:"
	@echo "  README.md              — \u9879\u76ee\u9996\u9875"
	@echo "  DEPLOYMENT.md        — \u90e8\u7f72\u6307\u5357"
	@echo "  CHANGELOG.md         — \u53d8\u66f4\u65e5\u5fd7"
	@echo "  CONTRIBUTING.md    — \u8d21\u732e\u6307\u5357"
	@echo "  docs/ARCHITECTURE.md — \u67b6\u6784\u8bf4\u660e"
	@echo "  docs/OPERATIONS.md   — \u64cd\u4f5c\u624b\u518c"
	@echo "  docs/TEST_REPORT.md — \u6d4b\u8bd5\u62a5\u544a"
	@echo "  docs/DELIVERY.md    — \u4ea4\u4ed8\u6e05\u5355"

version: ## 显示版本号
	@cat VERSION
