# FIN-L4 家庭理财管理系统 - 生产镜像
# 依赖: L4 框架(fin_l4) + L3 通用模块(fin001_account ~ fin006_advisor)
FROM python:3.12-slim

# 非 root 运行（安全）
RUN groupadd -r fin4 && useradd -r -g fin4 -d /app fin4

WORKDIR /app

# 依赖层（利用 Docker 层缓存）
# 使用 pip 镜像加速（可用 PIP_INDEX_URL 覆盖）
COPY fin_l4/requirements.txt /app/fin_l4/requirements.txt
RUN pip install --no-cache-dir --timeout 60 --retries 10 \
    -i ${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple} \
    -r /app/fin_l4/requirements.txt

# 应用代码: L4 框架 + L3 通用业务模块（L4 继承 L3 的运行时依赖）
COPY fin_l4/ /app/fin_l4/
COPY fin001_account/ /app/fin001_account/
COPY fin002_loan/ /app/fin002_loan/
COPY fin003_insurance/ /app/fin003_insurance/
COPY fin004_rate/ /app/fin004_rate/
COPY fin005_portfolio/ /app/fin005_portfolio/
COPY fin006_advisor/ /app/fin006_advisor/
COPY .env.example /app/.env.example

# 数据目录（挂载卷）
RUN mkdir -p /data && chown -R fin4:fin4 /app /data
VOLUME ["/data"]

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8500/', timeout=3)" || exit 1

USER fin4

ENV FIN4_HOST=0.0.0.0 \
    FIN4_PORT=8500 \
    FIN4_DB_DIR=/data \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8500

CMD ["python3", "-m", "fin_l4.run_web"]
