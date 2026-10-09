# 企微文档系统自动化数据采集详细设计

## 1. 环境信息

| 要素 | 值 |
|---|---|
| 目标系统名称 | 企业微信（WeCom）智能表格 / 文档 |
| 系统入口URL | `https://doc.weixin.qq.com/sheet/e3_AewA9wbYAJkCNWXLLXtMASV6kFQG5?scode=AD8AYAehAA801jsTMu` |
| 环境类型 | 生产 |
| 浏览器类型及版本 | Google Chrome 最新稳定版 |
| 自动化框架 | wecom_mcp API（首选） / 浏览器自动化（备选） |
| 操作系统 | macOS 14+ |

## 2. 认证信息

| 要素 | 值 |
|---|---|
| 认证方式 | 企微 API（wecom_mcp MCP tool） |
| 登录方式 | 企微插件自动鉴权 |
| 认证前提 | wecom-preflight 白名单检查 |
| 备选认证 | 浏览器自动化 + IAM SSO |

## 3. 采集路径

| 要素 | 值 |
|---|---|
| 采集方式 | wecom_mcp MCP tool → smartsheet_get_records |
| 备选方式 | wecom_mcp MCP tool → get_doc_content（异步轮询） |
| 降级方式 | 浏览器自动化访问企微 Web 端 |
| 最终降级 | 本机导入（Rex 手动导出 CSV） |

## 4. 数据源定义

| 数据源 | 文档类型 | 内容 |
|---|---|---|
| 确收凭证 | 智能表格（smartsheet, doc_type=10） | 确收交接数据 |
| 验收凭证 | 智能表格（smartsheet, doc_type=10） | 验收交接数据 |

**智能表格 URL**：
```
https://doc.weixin.qq.com/sheet/e3_AewA9wbYAJkCNWXLLXtMASV6kFQG5?scode=AD8AYAehAA801jsTMu
```

## 5. 字段定义

**确收凭证核心字段**：
- 标题、ID、BI履约ID、合同编号、客户名称、销售部门、项目经理、交接日期、财务、是否接收

**验收凭证核心字段**：
- 合同名称、标题、ID、BI履约ID、验收单编号、合同编号、客户名称、项目经理、交接日期、验收方式

## 6. 采集策略

| 要素 | 值 |
|---|---|
| 优先级 1 | wecom_mcp smartsheet_get_records（直接读取记录） |
| 优先级 2 | wecom_mcp get_doc_content（异步轮询） |
| 优先级 3 | 浏览器自动化访问企微 Web 端 |
| 优先级 4 | 本机导入（手动导出 CSV） |

## 7. 结果处理

| 要素 | 值 |
|---|---|
| 文件保存方式 | Python 脚本直接写入 |
| 文件格式 | CSV + JSON |
| 文件名格式 | `revenue_{YYYYMM}.csv` / `acceptance_{YYYYMM}.csv` |
| 归档目录 | `~/.openclaw/data/wecom_exports/` |

## 8. 异常处理

| 异常场景 | 处理方式 |
|---|---|
| wecom_mcp 不可用 | 降级到浏览器自动化 |
| API 权限不足 | 降级到本机导入 |
| 文档内容为空 | 重试3次，仍失败则报错 |
| 网络中断 | 检查网络，尝试重连 |

## 9. 关键经验

1. **wecom_mcp 是 MCP tool**：需要通过 OpenClaw tool 系统调用，不在主会话直接可用
2. **首次调用需 wecom-preflight**：检查白名单权限
3. **备选方案**：Rex 手动从 WeCom 导出 CSV，脚本读取本地文件
4. **数据在同一智能表格**：确收凭证和验收凭证在同一个智能表格里

## 10. 代码实现

```python
"""企微文档数据采集器"""
import json
import csv
from pathlib import Path
from typing import Optional

EXPORT_DIR = Path.home() / ".openclaw" / "data" / "wecom_exports"

WECOM_DOC_URL = "https://doc.weixin.qq.com/sheet/e3_AewA9wbYAJkCNWXLLXtMASV6kFQG5?scode=AD8AYAehAA801jsTMu"
WECOM_DOC_TYPE = "smartsheet"

LOCAL_REVENUE_CSV = (
    Path.home() / "Bangcle Workspace" / "01. Management" / "2026" / "2026团队报告" / "202606" / "202606确收凭证交接-确收.csv"
)
LOCAL_ACCEPTANCE_CSV = (
    Path.home() / "Bangcle Workspace" / "01. Management" / "2026" / "2026团队报告" / "202606" / "202606确收凭证交接-验收.csv"
)


def collect_from_api(month: str) -> Optional[dict]:
    """通过 wecom_mcp API 采集数据（优先级 1）"""
    # 通过 OpenClaw tool 系统调用 wecom_mcp
    # smartsheet_get_records 直接读取记录
    pass


def collect_from_local(month: str) -> Optional[dict]:
    """从本地 CSV 文件采集数据（降级方案）"""
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    
    try:
        import pandas as pd
    except ImportError:
        print("ERROR: pandas 未安装")
        return None
    
    result = {}
    
    # 确收凭证
    if LOCAL_REVENUE_CSV.exists():
        df_rev = pd.read_csv(LOCAL_REVENUE_CSV, encoding="utf-8-sig", low_memory=False)
        core_cols = ["标题", "ID", "BI履约ID", "合同编号", "客户名称", "销售部门", "项目经理", "交接日期", "财务", "是否接收"]
        available_cols = [c for c in core_cols if c in df_rev.columns]
        df_rev = df_rev[available_cols]
        df_rev = df_rev.dropna(how="all", subset=["标题", "合同编号"])
        
        rev_file = EXPORT_DIR / f"revenue_{month}.csv"
        df_rev.to_csv(rev_file, index=False, encoding="utf-8-sig")
        result["revenue"] = {"file": str(rev_file), "count": len(df_rev)}
    
    # 验收凭证
    if LOCAL_ACCEPTANCE_CSV.exists():
        df_acc = pd.read_csv(LOCAL_ACCEPTANCE_CSV, encoding="utf-8-sig", low_memory=False)
        core_cols = ["合同名称", "标题", "ID", "BI履约ID", "验收单编号-财务端", "合同编号", "客户名称", "项目经理", "交接日期", "验收方式"]
        available_cols = [c for c in core_cols if c in df_acc.columns]
        df_acc = df_acc[available_cols]
        df_acc = df_acc.dropna(how="all", subset=["标题", "合同编号"])
        
        acc_file = EXPORT_DIR / f"acceptance_{month}.csv"
        df_acc.to_csv(acc_file, index=False, encoding="utf-8-sig")
        result["acceptance"] = {"file": str(acc_file), "count": len(df_acc)}
    
    return result if result else None
```
