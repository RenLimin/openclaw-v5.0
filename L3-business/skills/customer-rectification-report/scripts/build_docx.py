# -*- coding: utf-8 -*-
"""
由结构化 report.yaml 渲染《项目复盘与整改报告》docx（六章四附件）。
用法:
  python3 build_docx.py report.yaml --out internal.docx [--external] [--template t.docx]
内部版：技术表第8列=ONES 对应；--external：改“参考”并剔除 ones/合同号等内部数据。
字体/字号遵循 assets/style-spec.json（宋体/黑体 + Times New Roman）。
"""
import sys, argparse, datetime, copy
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.section import WD_ORIENT, WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import json, os

HERE=os.path.dirname(os.path.abspath(__file__))
SPEC=json.load(open(os.path.join(HERE,'..','assets','style-spec.json'),encoding='utf-8'))
SONG='宋体'; HEI='黑体'; TNR='Times New Roman'

def set_font(run, ea=SONG, size=10.5, bold=False):
    run.font.name=TNR; run.font.size=Pt(size); run.font.bold=bold
    rpr=run._r.get_or_add_rPr(); rf=rpr.find(qn('w:rFonts'))
    if rf is None:
        rf=OxmlElement('w:rFonts'); rpr.insert(0,rf)
    for a in ('w:ascii','w:hAnsi','w:cs'): rf.set(qn(a),TNR)
    rf.set(qn('w:eastAsia'),ea)

def para(doc,text,ea=SONG,size=10.5,bold=False,align=None,space_after=6,keep_next=False):
    p=doc.add_paragraph()
    if align is not None: p.alignment=align
    pf=p.paragraph_format; pf.space_after=Pt(space_after)
    if keep_next: pf.keep_with_next=True
    if text:
        r=p.add_run(text); set_font(r,ea,size,bold)
    return p

def h1(doc,text): return para(doc,text,HEI,13,True,space_after=8,keep_next=True)
def h2(doc,text): return para(doc,text,HEI,11,True,space_after=6,keep_next=True)

def set_cell(cell,text,ea=SONG,size=9,bold=False,center=False):
    cell.text=""
    p=cell.paragraphs[0]
    if center: p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    lines=str(text).split("\n")
    r=p.add_run(lines[0]); set_font(r,ea,size,bold)
    for ln in lines[1:]:
        p2=cell.add_paragraph(); r=p2.add_run(ln); set_font(r,ea,size,bold)
        if center: p2.alignment=WD_ALIGN_PARAGRAPH.CENTER

def make_table(doc, headers, rows, size=9, widths=None, header_ea=HEI):
    t=doc.add_table(rows=1,cols=len(headers)); t.style='Table Grid'; t.alignment=WD_TABLE_ALIGNMENT.CENTER
    t.autofit=True
    for j,h in enumerate(headers): set_cell(t.rows[0].cells[j],h,header_ea,size,True,True)
    for row in rows:
        cells=t.add_row().cells
        for j,v in enumerate(row): set_cell(cells[j],v if v is not None else "",SONG,size)
    if widths:
        for j,w in enumerate(widths):
            for r in t.rows:
                r.cells[j].width=Cm(w)
    return t

def add_footer(sec, page=False):
    f=sec.footer; f.is_linked_to_previous=False
    p=f.paragraphs[0]; p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    r=p.add_run("稳如泰山 · 值得托付"); set_font(r,SONG,9)
    if page:
        run=p.add_run("   ")
        fld=OxmlElement('w:fldSimple'); fld.set(qn('w:instr'),'PAGE')
        rn=OxmlElement('w:r'); t2=OxmlElement('w:t'); t2.text="1"; rn.append(t2); fld.append(rn)
        p._p.append(fld)

def landscape_section(doc):
    sec=doc.add_section(WD_SECTION.NEW_PAGE)
    sec.orientation=WD_ORIENT.LANDSCAPE
    sec.page_width, sec.page_height = sec.page_height, sec.page_width
    sec.left_margin=Cm(1.5); sec.right_margin=Cm(1.5)
    return sec

def portrait_section(doc):
    sec=doc.add_section(WD_SECTION.NEW_PAGE)
    sec.orientation=WD_ORIENT.PORTRAIT
    sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
    sec.left_margin=Cm(2.5); sec.right_margin=Cm(2.5)
    return sec

def load_yaml(path):
    try: import yaml
    except ImportError:
        # 极简兜底：环境无 pyyaml 时给明确报错
        raise SystemExit("需要 pyyaml：pip install pyyaml")
    with open(path,encoding='utf-8') as f: return yaml.safe_load(f)

def build(data, external=False):
    doc=Document()
    sec=doc.sections[0]
    sec.page_width,sec.page_height=Cm(21.0),Cm(29.7)
    sec.left_margin=Cm(2.5); sec.right_margin=Cm(2.5)
    add_footer(sec,page=True)
    m=data['meta']
    # 封面
    for _ in range(3): para(doc,"",space_after=6)
    para(doc,m['client_full'],HEI,22,True,WD_ALIGN_PARAGRAPH.CENTER,space_after=10)
    para(doc,m['title'],HEI,26,True,WD_ALIGN_PARAGRAPH.CENTER,space_after=10)
    para(doc,m.get('subtitle',''),HEI,13,False,WD_ALIGN_PARAGRAPH.CENTER,space_after=24)
    info=[("提交单位",m['vendor_full']),("项目集经理",m.get('program_manager','')),
          ("在服合同",f"{len(data.get('contracts',[]))} 份"),
          ("问题范围",f"贵司正式反馈问题 {m['issue_count']} 条（100% 覆盖）"),
          ("编制日期",m['date']),("版本",m['version'])]
    it=make_table(doc,["项","内容"],info,size=10.5,widths=[4,11])
    doc.add_page_break()

    # 一 复盘说明
    h1(doc,"一　复盘说明")
    para(doc,f"我司就{len(data.get('contracts',[]))}个在服项目截至当前的交付情况专项复盘。"
             f"本报告依据{m.get('trigger_meeting','现场沟通')}及贵司正式反馈的 {m['issue_count']} 条问题编制，"
             "逐条给出整改措施、责任方、时限与验收标准。")
    # 二 背景
    h1(doc,"二　项目与合同背景")
    cs=data.get('contracts',[])
    para(doc,f"在服合同 {len(cs)} 份，按项目集统一管理。")
    crows=[[c.get('no',''),c.get('name',''),c.get('amount',''),c.get('period','')] for c in cs]
    if external:
        for r in crows: r[0]=re_mask(r[0])
    make_table(doc,["合同编号","项目（合同）名称","金额(元)","服务期"],crows,size=9,widths=[3.2,6.5,2.5,4])

    # 三 问题与整改（横向）
    landscape_section(doc)
    h1(doc,f"三　贵司问题与整改措施（{m['issue_count']} 条全覆盖）")
    groups=[('deliver',"（一）交付管理类"),('tech',"（二）技术能力类")]
    wide=[1.2,2.0,4.5,5.5,2.6,3.0,3.6,2.6]
    for gkey,gtitle in groups:
        items=[i for i in data['issues'] if i.get('group')==gkey]
        if not items: continue
        h2(doc,gtitle)
        if external:
            headers=["编号","类别","贵司问题","整改措施","责任方","完成时限","验收标准","参考"]
        else:
            last="ONES 对应" if gkey=='tech' else "参考"
            headers=["编号","类别","贵司问题","整改措施","责任方","完成时限","验收标准",last]
        rows=[]
        for i in items:
            lastv = i.get('ref','') if (external or gkey=='deliver') else i.get('ones','')
            rows.append([i['id'],i.get('cat',''),i.get('question',''),i.get('action',''),
                         i.get('owner',''),i.get('due',''),i.get('acceptance',''),lastv])
        make_table(doc,headers,rows,size=8,widths=wide)

    # 四–六 回到纵向
    portrait_section(doc)
    h1(doc,"四　总体整改机制")
    for bullet in data.get('mechanism',[]):
        para(doc,"● "+bullet)
    h1(doc,"五　实施安排")
    make_table(doc,["阶段","时间窗口","重点内容"],
               [[p.get('stage',''),p.get('window',''),p.get('focus','')] for p in data.get('phases',[])],
               size=9,widths=[3,4,9])
    h1(doc,"六　近期重点行动")
    make_table(doc,["序号","重点行动","责任方","计划完成"],
               [[a['no'],a.get('action',''),a.get('owner',''),a.get('due','')] for a in data.get('actions',[])],
               size=9,widths=[1.5,8.5,3.5,3])
    para(doc,"我司将严格兑现上述整改承诺，通过共享台账等持续向贵司透明同步进展。",space_after=18)
    para(doc,m['vendor_full'],SONG,11,False,WD_ALIGN_PARAGRAPH.RIGHT)
    para(doc,m['date'],SONG,11,False,WD_ALIGN_PARAGRAPH.RIGHT)

    # 附件
    doc.add_page_break()
    h1(doc,"附件 1　结构化变更同步模板")
    make_table(doc,["字段","填写内容"],
               [[f.get('field',''),f.get('content','')] for f in data.get('annex1_fields',[])],
               size=9,widths=[4,12])
    h1(doc,"附件 2　交付物清单")
    dvs=data.get('deliverables',[])
    if external:
        dvs=[d for d in dvs]  # 内容本身不应含合同号，validate G8/G4 兜底
    make_table(doc,["交付类型","交付物","内容 / 要求"],
               [[d.get('type',''),d.get('name',''),d.get('requirement','')] for d in dvs],
               size=9,widths=[3.5,5.5,7])
    landscape_section(doc)
    h1(doc,"附件 3　技术 A/B 角名单")
    make_table(doc,["技术方向","A 角（主责）","B 角（备援）","职能团队负责人"],
               [[r.get('domain',''),r.get('a',''),r.get('b',''),r.get('lead','')] for r in data.get('ab_roles',[])],
               size=9,widths=[5,4,4,4])
    portrait_section(doc)
    h1(doc,"附件 4　主动通报机制")
    make_table(doc,["环节","触发条件","动作","时限","责任方"],
               [[r.get('stage',''),r.get('trigger',''),r.get('action',''),r.get('sla',''),r.get('owner','')]
                for r in data.get('notify',[])],size=9,widths=[2.5,4,5,3,3])
    para(doc,"注：本机制与共享工单台账、周例会及周报模板配套使用；贵司沟通群同步责任人、进展与预计解决时间。",SONG,9)
    return doc

import re
def re_mask(s): return re.sub(r'XSZS\s*\d{6,}','',str(s))

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('yaml'); ap.add_argument('--out',required=True)
    ap.add_argument('--external',action='store_true'); ap.add_argument('--template',default=None)
    a=ap.parse_args()
    data=load_yaml(a.yaml)
    if a.template:
        raise SystemExit("基于官方模板的渲染请在有模板环境运行；当前内置渲染不带品牌页眉（页脚标语/页码已含）。")
    doc=build(data,external=a.external); doc.save(a.out)
    print("saved",a.out,"EXTERNAL" if a.external else "INTERNAL")

if __name__=='__main__': main()
