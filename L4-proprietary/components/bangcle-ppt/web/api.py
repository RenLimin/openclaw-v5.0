"""
Bangcle PPT Web API — FastAPI 路由
基于 bangcle_ppt 引擎封装，不重复业务逻辑。
"""

from __future__ import annotations

import io
import os
import sys
import tempfile
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Body
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import yaml

# 模块路径
_WEB_DIR = os.path.dirname(os.path.abspath(__file__))
_PKG_ROOT = os.path.dirname(_WEB_DIR)
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from bangcle_ppt import TemplateEngine, REGISTRY
from bangcle_ppt.dsl.schema import PresentationSpec, PAGE_LAYOUT_MAP

router = APIRouter(prefix="/api", tags=["ppt"])


# ── 工具 ────────────────────────────────────────────────────────────

def _get_engine(theme: str = "light") -> TemplateEngine:
    templates_dir = os.path.join(_PKG_ROOT, "bangcle_ppt", "templates")
    engine = TemplateEngine(templates_dir=templates_dir, theme=theme)
    engine.register_renderers(REGISTRY)
    return engine


def _list_all_templates() -> list[dict[str, Any]]:
    """返回所有主题下所有模板的摘要信息。"""
    result = []
    for theme in ["light", "dark"]:
        engine = _get_engine(theme=theme)
        for name in sorted(engine.list_templates(theme=theme)):
            try:
                tpl = engine.load_template(name, theme=theme)
                result.append({
                    "name": name,
                    "theme": theme,
                    "title": tpl.meta.name,
                    "description": tpl.meta.description,
                    "category": tpl.meta.category,
                    "page_type": tpl.meta.page_type,
                })
            except Exception:
                result.append({
                    "name": name,
                    "theme": theme,
                    "title": name,
                    "description": "",
                    "category": "unknown",
                    "page_type": name,
                })
    return result


# ── Schemas ─────────────────────────────────────────────────────────

class RenderRequest(BaseModel):
    """渲染请求体。"""
    dsl_yaml: str = Field(..., min_length=1, description="完整 DSL YAML 字符串")
    theme: Optional[str] = Field(None, pattern="^(light|dark)$", description="可选主题覆盖")
    filename: Optional[str] = Field(None, max_length=200, description="下载文件名")


class ValidateResponse(BaseModel):
    valid: bool
    title: str = ""
    theme: str = ""
    slide_count: int = 0
    errors: list[str] = Field(default_factory=list)


# ── API ─────────────────────────────────────────────────────────────

@router.get("/health")
async def api_health():
    """健康检查。"""
    return {"status": "ok", "component": "bangcle-ppt-web", "version": "1.0.0"}


@router.get("/templates")
async def api_list_templates(
    theme: Optional[str] = Query(None, pattern="^(light|dark)$"),
    category: Optional[str] = None,
):
    """模板列表。"""
    all_tpls = _list_all_templates()
    if theme:
        all_tpls = [t for t in all_tpls if t["theme"] == theme]
    if category:
        all_tpls = [t for t in all_tpls if t["category"] == category]
    return {
        "total": len(all_tpls),
        "templates": all_tpls,
    }


@router.get("/templates/{template_name}")
async def api_template_detail(template_name: str):
    """模板详情（schema + 示例数据）。"""
    # 推断主题
    theme = "dark" if template_name.endswith("-dark") else "light"
    engine = _get_engine(theme=theme)

    tpl = None
    actual_theme = theme
    try:
        tpl = engine.load_template(template_name, theme=theme)
    except FileNotFoundError:
        # 尝试另一个主题
        other = "dark" if theme == "light" else "light"
        try:
            tpl = engine.load_template(template_name, theme=other)
            actual_theme = other
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"模板不存在: {template_name}")

    layout_cls = PAGE_LAYOUT_MAP.get(template_name)
    fields = []
    if layout_cls:
        for fname, field in layout_cls.model_fields.items():
            ftype = (
                field.annotation.__name__
                if hasattr(field.annotation, "__name__")
                else str(field.annotation)
            )
            fields.append({
                "name": fname,
                "type": ftype,
                "default": field.default if field.default is not None else None,
                "description": field.description or "",
            })

    return {
        "name": template_name,
        "theme": actual_theme,
        "meta": {
            "title": tpl.meta.name,
            "page_type": tpl.meta.page_type,
            "description": tpl.meta.description,
            "version": tpl.meta.version,
            "category": tpl.meta.category,
            "author": tpl.meta.author,
        },
        "layout_fields": fields,
        "sample_data": tpl.data,
        "sample_dsl": yaml.dump(
            {
                "meta": tpl.meta.model_dump(),
                "layout": tpl.layout,
                "data": tpl.data,
            },
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        ),
    }


@router.post("/validate")
async def api_validate(body: dict[str, Any] = Body(...)):
    """校验 DSL YAML。"""
    dsl_yaml = body.get("dsl_yaml", "")
    if not dsl_yaml:
        raise HTTPException(status_code=400, detail="dsl_yaml 不能为空")

    try:
        raw = yaml.safe_load(dsl_yaml)
        if not isinstance(raw, dict):
            return ValidateResponse(
                valid=False,
                errors=["顶层必须是 dict"],
            ).model_dump()
        spec = PresentationSpec(**raw)
    except Exception as e:
        return ValidateResponse(
            valid=False,
            errors=[str(e)],
        ).model_dump()

    errors: list[str] = []
    for i, slide in enumerate(spec.slides, 1):
        try:
            slide.validate_layout_against_type()
        except Exception as e:
            errors.append(f"第 {i} 页 ({slide.meta.page_type}): {e}")

    return ValidateResponse(
        valid=len(errors) == 0,
        title=spec.title,
        theme=spec.theme,
        slide_count=len(spec.slides),
        errors=errors,
    ).model_dump()


@router.post("/render")
async def api_render(body: RenderRequest):
    """渲染 DSL 生成 PPT，返回文件下载。"""
    try:
        raw = yaml.safe_load(body.dsl_yaml)
        if not isinstance(raw, dict):
            raise HTTPException(status_code=400, detail="DSL 顶层必须是 dict")
        spec = PresentationSpec(**raw)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"DSL 解析失败: {e}")

    # 校验所有 slide layout
    errors: list[str] = []
    for i, slide in enumerate(spec.slides, 1):
        try:
            slide.validate_layout_against_type()
        except Exception as e:
            errors.append(f"第 {i} 页 ({slide.meta.page_type}): {e}")
    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))

    theme = body.theme or spec.theme
    engine = _get_engine(theme=theme)

    # 渲染到临时文件
    with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        engine.render_from_spec(spec, tmp_path)
    except Exception as e:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise HTTPException(status_code=500, detail=f"渲染失败: {e}")

    # 读取文件内容
    try:
        with open(tmp_path, "rb") as f:
            content = f.read()
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    from urllib.parse import quote
    raw_filename = body.filename or f"{spec.title or 'presentation'}.pptx"
    if not raw_filename.endswith(".pptx"):
        raw_filename += ".pptx"
    # 使用 ASCII 安全文件名 + RFC 5987 UTF-8 编码，支持中文
    ascii_name = raw_filename.encode("ascii", "replace").decode("ascii").replace("?", "_")
    utf8_name = quote(raw_filename)

    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={
            "Content-Disposition": f"attachment; filename='{ascii_name}'; filename*=UTF-8''{utf8_name}",
            "Content-Length": str(len(content)),
        },
    )


@router.get("/templates/{template_name}/preview")
async def api_template_preview(template_name: str, theme: Optional[str] = None):
    """单模板预览 PPT 下载。"""
    t = theme or ("dark" if template_name.endswith("-dark") else "light")
    engine = _get_engine(theme=t)

    try:
        tpl = engine.load_template(template_name, theme=t)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"模板不存在: {template_name}")

    with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        engine.render_presentation(
            [(template_name, tpl.data)],
            tmp_path,
            theme=t,
        )
        with open(tmp_path, "rb") as f:
            content = f.read()
    except Exception as e:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise HTTPException(status_code=500, detail=f"渲染失败: {e}")
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    from urllib.parse import quote
    fname = f"preview-{template_name}.pptx"
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={
            "Content-Disposition": f"attachment; filename='{fname}'; filename*=UTF-8''{quote(fname)}",
            "Content-Length": str(len(content)),
        },
    )
