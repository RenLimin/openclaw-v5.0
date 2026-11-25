# -*- coding: utf-8 -*-
"""
客户《项目复盘与整改报告》fail-closed 机器门禁。
用法:
  python3 validate_report.py <docx> [--n N] [--external] [--pdf out.pdf]
exit=0 PASS; 非0 BLOCK（打印违例清单）。
G2-G9 基于 docx 静态检查；G1 需 PDF（--pdf，可选，需 pymupdf）。
"""
import sys, re, json, argparse, os
from docx import Document
from docx.oxml.ns import qn

W = qn('w:r')
HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = json.load(open(os.path.join(HERE, '..', 'assets', 'style-spec.json'), encoding='utf-8'))

# 时限解析：支持 已完成 / YYYY-MM-DD / YYYY-MM-DD ~ MM-DD(或YYYY-MM-DD) / YYYY-MM-DD起...跟进 / 跟进中
DATE   = r'(\d{4})-(\d{2})-(\d{2})'
SHORT  = r'(\d{2})-(\d{2})'
RUN_RE = re.compile(DATE + r'\s*起')
WIN_RE = re.compile(DATE + r'\s*[~～-]\s*(?:(\d{4})?-?)?(\d{2})-(\d{2})')
DAY_RE = re.compile(DATE)

def ymd(y,m,d): 
    import datetime; return datetime.date(int(y),int(m),int(d))

def parse_due(s):
    """返回 (kind, start, end)；kind in done/window/day/running/follow/bad"""
    s=s.strip()
    if s in ('已完成',''):
        return ('done' if s=='已完成' else 'bad', None, None)
    if '起' in s:
        m=RUN_RE.search(s)
        if m: return ('running', ymd(*m.groups()), ymd(*m.groups()))
        return ('bad',None,None)
    if s=='跟进中': return ('follow',None,None)
    m=WIN_RE.search(s)
    if m:
        y,mo,da,y2,mo2,da2=m.groups()
        st=ymd(y,mo,da); en=ymd(y2 or y,mo2,da2)
        return ('window', st, en)
    m=DAY_RE.search(s)
    if m and re.fullmatch(r'\s*'+DATE+r'\s*', s):
        d=ymd(*m.groups()); return ('day',d,d)
    if '跟进' in s and DAY_RE.search(s):  # 日期+按日/周跟进（无"起"字也算连续）
        d=ymd(*DAY_RE.search(s).groups()); return ('running',d,d)
    return ('bad',None,None)

def cell_text(c): return c.text.strip()
def table_header(t): return [cell_text(c) for c in t.rows[0].cells]

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('docx'); ap.add_argument('--n',type=int,default=None)
    ap.add_argument('--external',action='store_true'); ap.add_argument('--pdf',default=None)
    a=ap.parse_args()
    errs=[]; warns=[]
    d=Document(a.docx)
    body=d.element.body
    full_text="\n".join(p.text for p in d.paragraphs)
    for t in d.tables:
        for r in t.rows:
            full_text+="\n"+"\t".join(c.text for c in r.cells)

    # ---------- 定位整改表（含 编号+整改措施+完成时限+验收标准） ----------
    issue_tables=[]; deliv=None
    for t in d.tables:
        h=table_header(t)
        if {'编号','整改措施','责任方','完成时限','验收标准'} <= set(h):
            issue_tables.append(t)
        if '交付类型' in h and '交付物' in h:
            deliv=t
    if not issue_tables: errs.append("G2: 未找到问题整改表（编号/整改措施/责任方/完成时限/验收标准）")

    # ---------- G2 覆盖 + 四必填 + 时限白名单 + 禁词 ----------
    issue_rows=[]
    for t in issue_tables:
        h=table_header(t); idx={k:h.index(k) for k in ('编号','整改措施','责任方','完成时限','验收标准')}
        for r in t.rows[1:]:
            cells=r.cells
            if not cell_text(cells[idx['编号']]): continue
            issue_rows.append((h,cells,idx))
    if a.n is not None and len(issue_rows)!=a.n:
        errs.append(f"G2: 问题条数 {len(issue_rows)} != 声明 N={a.n}")
    for h,cells,idx in issue_rows:
        no=cell_text(cells[idx['编号']])
        for k in ('整改措施','责任方','完成时限','验收标准'):
            if not cell_text(cells[idx[k]]): errs.append(f"G2: 第{no}条缺「{k}」")
        kind,_,_=parse_due(cell_text(cells[idx['完成时限']]))
        if kind=='bad': errs.append(f"G2: 第{no}条完成时限不合法: {cell_text(cells[idx['完成时限']])!r}")
    for term in SPEC['banned_terms']:
        if term in full_text: errs.append(f"G2/G6: 出现禁词 {term!r}")

    # ---------- G3 行动日期 vs 明细窗口边界一致 ----------
    if issue_rows:
        bounds=set(); starts=set()
        for h,cells,idx in issue_rows:
            kind,st,en=parse_due(cell_text(cells[idx['完成时限']]))
            if kind in ('window','day'): bounds|={st,en}; starts.add(st)
            if kind=='running': starts.add(st); bounds.add(st)
        act_tbl=None
        for t in d.tables:
            h=table_header(t)
            if '重点行动' in h and '计划完成' in h: act_tbl=t; break
        if act_tbl is None: warns.append("G3: 未找到近期重点行动表")
        else:
            ah=table_header(t) if False else table_header(act_tbl)
            di=ah.index('计划完成')
            for r in act_tbl.rows[1:]:
                v=cell_text(r.cells[di]); kind,st,en=parse_due(v)
                if kind in ('day','window'):
                    if en not in bounds: errs.append(f"G3: 行动完成日 {v} 不是任何明细窗口边界（与第三章不一致）")
                elif kind=='running':
                    if st not in starts: errs.append(f"G3: 行动起算日 {v} 不是任何明细起始边界（与第三章不一致）")
                elif kind=='bad':
                    errs.append(f"G3: 行动日期不合法 {v!r}")

    # ---------- G4 附件2 三类齐全 + 无合同来源 ----------
    if deliv is None:
        errs.append("G4: 未找到附件2交付物清单（交付类型/交付物）")
    else:
        h=table_header(deliv); ti=h.index('交付类型')
        types_text="\n".join(cell_text(r.cells[ti]) for r in deliv.rows[1:])
        for need in SPEC['deliverable_types']:
            if need not in types_text: errs.append(f"G4: 附件2 缺交付类型 {need!r}")
        dtext="\n".join("\t".join(c.text for c in r.cells) for r in deliv.rows)
        for bad,pat in [('合同号 XSZS',r'XSZS\s*\d{6,}'),('§条款',r'§\s*\d'),('合同第x条',r'合同?第?\s*\d+\s*条'),('数据来源/依据',r'(数据来源|来源依据|依据[:：])')]:
            if re.search(pat,dtext): errs.append(f"G4: 附件2 残留{bad}")
        for r in deliv.rows[1:]:
            if not cell_text(r.cells[h.index('交付物')]): errs.append("G4: 存在空交付物行")

    # ---------- G5 字体/字号显式合规 ----------
    allowed=set(SPEC['sizes_pt']['allowed_half_values'])
    ea_ok=set(SPEC['fonts']['eastAsia_allowed'])
    n_run=0
    for r in body.iter(qn('w:r')):
        txt="".join(t.text or '' for t in r.iter(qn('w:t')))
        if not txt.strip(): continue
        n_run+=1
        rpr=r.find(qn('w:rPr'))
        if rpr is None: errs.append(f"G5: run 无 rPr: {txt[:12]!r}"); continue
        rf=rpr.find(qn('w:rFonts')); sz=rpr.find(qn('w:sz'))
        if rf is None: errs.append(f"G5: run 未显式声明字体: {txt[:12]!r}")
        else:
            ea=rf.get(qn('w:eastAsia'))
            if ea not in ea_ok: errs.append(f"G5: eastAsia={ea!r} 非允许字体 @ {txt[:12]!r}")
        if sz is None: errs.append(f"G5: run 未显式字号: {txt[:12]!r}")
        else:
            try: szv=int(sz.get(qn('w:val')))
            except ValueError: szv=-1
            if szv not in allowed:
                errs.append(f"G5: 字号 half={sz.get(qn('w:val'))} 不在枚举 @ {txt[:12]!r}")

    # ---------- G6 全称 ----------
    if SPEC and not re.search(r'银行|公司', full_text): pass
    meta_client_kw=['有限公司']
    if '有限公司' not in full_text: errs.append("G6: 缺少公司全称")

    # ---------- G7 修订残留 ----------
    for tag in ('w:ins','w:del','w:pPrChange','w:rPrChange'):
        n=len(body.findall(qn(tag)))
        if n: errs.append(f"G7: 修订残留 {tag} x{n}")

    # ---------- G8 对外脱敏 ----------
    if a.external:
        for t in d.tables:
            h=table_header(t)
            if any('ONES' in x.upper() for x in h): errs.append("G8: 对外版仍含 ONES 列")
        for pat,label in [(r'ones\.bangcle\.com','ONES URL'),(r'XSZS\s*\d{6,}','合同号'),(r'SSXM-\d{4}-\d{4}-\d{4}','ONES项目号')]:
            for m in re.finditer(pat,full_text): errs.append(f"G8: 对外版残留 {label}: …{m.group(0)}…")
        # 裸 6-7 位 ONES 任务号（排除 8 位日期、含逗号金额、年份上下文）
        for m in re.finditer(r'(?<![\d,])(\d{6,7})(?![\d,])',full_text):
            tok=m.group(0); ctx=full_text[max(0,m.start()-6):m.start()]
            if not re.search(r'(19|20)\d{2}$',ctx): errs.append(f"G8: 对外版疑似 ONES 任务号 {tok}")

    # ---------- G9 页眉 logo / 页脚标语+页码（遍历所有 header/footer 部件） ----------
    slogan=SPEC['footer_slogan']; foot_ok=False; pagefield=False; logo=False
    def iter_hf(kind):
        for rel in d.part.rels.values():
            if rel.reltype.endswith(f"/{kind}"):
                try: yield rel.target_part.blob.decode("utf-8","ignore")
                except Exception: pass
    fall="".join(iter_hf("footer")); hdrx="".join(iter_hf("header"))
    foot_ok = slogan in fall
    pagefield = ('PAGE' in fall) or ('PAGE' in "".join(iter_hf("footer")))
    logo = any(k in hdrx for k in ('blip','graphic','pict','imagedata'))
    if not foot_ok: errs.append("G9: 页脚缺标语「%s」"%slogan)
    if not pagefield: errs.append("G9: 页脚缺页码域")
    if not logo: warns.append("G9: 页眉未检测到 logo 图形（基于官方模板应有）")

    # ---------- G1 PDF 越界（可选） ----------
    if a.pdf:
        try:
            import pymupdf
            pdf=pymupdf.open(a.pdf)
            over=0
            for pg in pdf:
                for b in pg.get_text('blocks'):
                    if b[2]>pg.rect.width-2 or b[0]<2 or b[3]>pg.rect.height-2: over+=1
            if over: errs.append(f"G1: PDF 越界块 {over}")
        except Exception as e:
            warns.append(f"G1: PDF 检查跳过 ({e})")

    print(f"== validate_report.py :: {'EXTERNAL' if a.external else 'INTERNAL'} :: {a.docx}")
    print(f"问题条数={len(issue_rows)} 文本run={n_run} 违例={len(errs)} 警告={len(warns)}")
    for w in warns: print("  [WARN]",w)
    for e in errs: print("  [FAIL]",e)
    if errs:
        print("RESULT: BLOCK"); sys.exit(1)
    print("RESULT: PASS"); sys.exit(0)

if __name__=='__main__': main()
