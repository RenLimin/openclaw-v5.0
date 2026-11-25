# -*- coding: utf-8 -*-
"""customer-rectification-report 门禁回归：
- 用脱敏 fixture 渲染内部版/对外版，validate 必须 PASS；
- 5 类突变必须被 BLOCK；内部版当对外版必须 BLOCK。
"""
import os, subprocess, sys, copy
import pytest
from docx import Document

HERE=os.path.dirname(os.path.abspath(__file__))
ROOT=os.path.dirname(HERE)
BUILD=os.path.join(ROOT,"scripts","build_docx.py")
VAL=os.path.join(ROOT,"scripts","validate_report.py")
FIX=os.path.join(HERE,"fixtures","report.sample.yaml")
TMP="/tmp/crr_pytest"; os.makedirs(TMP,exist_ok=True)

def run_val(path, n=6, external=False):
    cmd=[sys.executable,VAL,path,"--n",str(n)]+(["--external"] if external else [])
    return subprocess.run(cmd,capture_output=True,text=True)

def build(external, out):
    cmd=[sys.executable,BUILD,FIX,"--out",out]+(["--external"] if external else [])
    r=subprocess.run(cmd,capture_output=True,text=True)
    assert r.returncode==0, r.stderr

def settext(cell,txt):
    p=cell.paragraphs[0]
    for r in list(p.runs): r._r.getparent().remove(r._r)
    p.add_run(txt)

def tables(d):
    iss=[]; deliv=None; act=None
    for t in d.tables:
        h=[c.text.strip() for c in t.rows[0].cells]
        if {'编号','整改措施','责任方','完成时限','验收标准'}<=set(h): iss.append((t,h))
        if '交付类型' in h: deliv=(t,h)
        if '重点行动' in h: act=(t,h)
    return iss,deliv,act

def test_internal_golden_passes():
    out=os.path.join(TMP,"internal.docx"); build(False,out)
    r=run_val(out); assert r.returncode==0, r.stdout

def test_external_passes_and_strips_ones():
    out=os.path.join(TMP,"external.docx"); build(True,out)
    r=run_val(out,external=True); assert r.returncode==0, r.stdout
    # 对外文档不得出现内部 ONES 标识
    txt="\n".join(p.text for p in Document(out).paragraphs)
    for t in Document(out).tables:
        for row in t.rows:
            txt+="\n"+"\t".join(c.text for c in row.cells)
    assert "ones." not in txt and "ON-1" not in txt
    heads=[c.text.strip() for tb in Document(out).tables for c in tb.rows[0].cells]
    assert not any("ONES" in x.upper() for x in heads)

def test_external_blocks_internal_docx():
    out=os.path.join(TMP,"internal2.docx"); build(False,out)
    r=run_val(out,external=True); assert r.returncode!=0

@pytest.mark.parametrize("mutation",["missing_acceptance","bad_action_date",
    "contract_in_deliverable","illegal_due","banned_term"])
def test_mutations_blocked(mutation):
    src=os.path.join(TMP,"internal.docx")
    if not os.path.exists(src): build(False,src)
    d=Document(src); iss,deliv,act=tables(d)
    if mutation=="missing_acceptance":
        t,h=iss[0]; settext(t.rows[1].cells[h.index('验收标准')],"")
    elif mutation=="bad_action_date":
        t,h=act; settext(t.rows[1].cells[h.index('计划完成')],"2026-11-26")
    elif mutation=="contract_in_deliverable":
        t,h=deliv; settext(t.rows[1].cells[h.index('内容 / 要求')],"依据 XSZS2608140597 第5.5条")
    elif mutation=="illegal_due":
        t,h=iss[0]; settext(t.rows[2].cells[h.index('完成时限')],"尽快完成")
    elif mutation=="banned_term":
        for tb in d.tables:
            h=[c.text.strip() for c in tb.rows[0].cells]
            if 'A 角（主责）' in h: settext(tb.rows[1].cells[1],"待指定"); break
    out=os.path.join(TMP,f"mut_{mutation}.docx"); d.save(out)
    r=run_val(out); assert r.returncode!=0, f"{mutation} 未被拦截\n{r.stdout}"
