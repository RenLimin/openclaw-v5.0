#!/usr/bin/env python3
"""风险分级规则正负例。"""
import promote as pg


def test_high_risk_credentials():
    assert pg.classify_risk("把 api_key 写进 MEMORY.md") == "high"
    assert pg.classify_risk("合同金额：120000 付款条款") == "high"
    assert pg.classify_risk("用户身份证号 310101...") == "high"
    assert pg.classify_risk("执行 force-push 到 main") == "high"


def test_low_risk_naming_template():
    assert pg.classify_risk("命名规范：统一 kebab-case") == "low"
    assert pg.classify_risk("模板对齐：6 份旧模板文档") == "low"
    assert pg.classify_risk("流程：先设计文档后写代码") == "low"


def test_medium_default():
    assert pg.classify_risk("今天天气不错") == "medium"
