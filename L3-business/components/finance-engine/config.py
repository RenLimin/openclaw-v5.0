"""FIN-L4 配置模块 — 支持环境变量 + .env 文件

优先级: 环境变量 > .env 文件 > 内置默认值
所有配置可通过 FIN4_* 环境变量覆盖，便于容器化与多服务器部署。
"""

import os
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """轻量 .env 加载（避免额外依赖 python-dotenv）"""
    if not path.exists():
        return
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            # 不覆盖已存在的环境变量（环境变量优先级更高）
            if key and key not in os.environ:
                os.environ[key] = value
    except OSError:
        pass


def _get_env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


# 加载 .env（项目根目录 > 当前目录）
_load_dotenv(PROJECT_ROOT / ".env")
_load_dotenv(Path(os.getcwd()) / ".env")


class Settings:
    """FIN-L4 运行时配置"""

    def __init__(self) -> None:
        # 服务监听
        self.host = os.getenv("FIN4_HOST", "127.0.0.1")
        self.port = _get_env_int("FIN4_PORT", 8500)

        # 数据目录（SQLite 存放位置）
        raw_db_dir = os.getenv("FIN4_DB_DIR")
        if raw_db_dir:
            self.db_dir = Path(raw_db_dir).expanduser()
        else:
            self.db_dir = Path(os.path.expanduser("~/.fin-l4"))
        self.db_dir.mkdir(parents=True, exist_ok=True)

        # 默认家庭 ID
        self.family_id = os.getenv("FIN4_FAMILY_ID", "default")

        # 应用元信息
        self.app_name = os.getenv("FIN4_APP_NAME", "FIN-L4 家庭理财管理系统")
        self.debug = os.getenv("FIN4_DEBUG", "0") == "1"

        # 外部链接只读模式（安全默认）
        self.external_readonly = os.getenv("FIN4_EXTERNAL_READONLY", "1") == "1"

    @property
    def db_path(self) -> str:
        return str(self.db_dir / "fin_l4.db")

    def to_dict(self) -> dict:
        return {
            "host": self.host,
            "port": self.port,
            "db_dir": str(self.db_dir),
            "db_path": self.db_path,
            "family_id": self.family_id,
            "app_name": self.app_name,
            "debug": self.debug,
            "external_readonly": self.external_readonly,
        }


# 模块级单例（惰性）
_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
