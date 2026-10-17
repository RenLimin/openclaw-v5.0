"""
conftest.py — pytest 配置 for 视觉回归测试
使用 playwright-pytest 提供 page fixture
"""

import pytest
from playwright.async_api import Page, Browser

# 配置 pytest-asyncio 异步模式
pytest_plugins = "pytest_asyncio"


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """自定义浏览器上下文参数"""
    return {
        **browser_context_args,
        "viewport": None,  # 禁用默认视口，由测试设置
    }
