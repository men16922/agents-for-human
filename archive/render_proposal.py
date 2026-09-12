"""Render the editable proposal into a standalone, offline HTML document."""
from pathlib import Path
import hashlib
import html
import re

import markdown
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent / "aftercare"
source = (ROOT / "proposal.md").read_text()

def slug(value, separator):
    match = re.match(r"(\d\d)\.", value)
    return f"section-{match.group(1)}" if match else re.sub(r"[^\w-]+", "-", value).strip("-").lower()

rendered = markdown.markdown(source, extensions=["tables", "fenced_code", "toc"],
    extension_configs={"toc": {"slugify": slug}})
soup = BeautifulSoup(rendered, "html.parser")
soup.h1.decompose()
# The document title, tagline and status are represented in the cover below.
for _ in range(2):
    soup.find("p").decompose()

for table in soup.find_all("table"):
    wrap = soup.new_tag("div", attrs={"class": "table-wrap", "tabindex": "0", "role": "region", "aria-label": "가로로 스크롤할 수 있는 표"})
    table.wrap(wrap)
for anchor in soup.select('a[href^="https://"]'):
    anchor["target"] = "_blank"
    anchor["rel"] = "noopener noreferrer"

headings = [(h["id"], h.get_text()) for h in soup.find_all("h2")]
nav = "".join(f'<a href="#{ident}"><span>{text[:2]}</span>{html.escape(text[4:])}</a>' for ident, text in headings)
parts = []
current = []
current_id = "overview"
for node in list(soup.contents):
    if getattr(node, "name", None) == "h2":
        if current:
            parts.append(f'<section class="document-section" aria-labelledby="{current_id}">' + "".join(current) + '</section>')
        current_id = node["id"]
        current = [str(node)]
    else:
        current.append(str(node))
if current:
    parts.append(f'<section class="document-section" aria-labelledby="{current_id}">' + "".join(current) + '</section>')
body = "".join(parts)

css = r"""
:root{--paper:#f7f6f2;--surface:#fff;--ink:#17252b;--muted:#5c6b71;--line:#dde3df;--accent:#b64623;--teal:#236859;--navy:#183d40;--tint:#eaf1eb}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:90px}body{margin:0;background:var(--paper);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Noto Sans KR","Malgun Gothic",sans-serif;line-height:1.85;word-break:keep-all;overflow-wrap:break-word}a{color:var(--teal);text-underline-offset:4px}a:focus-visible,button:focus-visible,summary:focus-visible,[tabindex]:focus-visible{outline:3px solid #cd7c42;outline-offset:4px}.skip-link{position:absolute;top:-100px;left:20px;z-index:100}.skip-link:focus{top:12px;background:white;padding:12px}
.topbar{position:sticky;top:0;z-index:10;height:70px;display:flex;align-items:center;justify-content:space-between;padding:0 4.5vw;background:rgba(247,246,242,.97);border-bottom:1px solid var(--line);gap:20px}.brand{display:flex;align-items:center;gap:10px;color:var(--ink);text-decoration:none;font-weight:800;font-size:21px;letter-spacing:-.7px}.brand-mark{width:29px;height:29px;border-radius:50%;background:var(--teal);display:grid;place-items:center;color:white;font-size:18px}.topnav{display:flex;align-items:center;gap:24px;font-size:13px}.topnav a{color:var(--muted);text-decoration:none}.topnav a:hover{color:var(--accent)}button{font:inherit;cursor:pointer}.print-btn{border:1px solid #bbc8c0;border-radius:6px;background:transparent;padding:6px 14px;font-size:12px;color:var(--ink)}
.cover{max-width:1330px;margin:0 auto;padding:70px 45px 52px}.eyebrow{font-size:11px;letter-spacing:1.7px;font-weight:750;color:var(--teal);margin-bottom:24px}.cover-grid{display:grid;grid-template-columns:1.22fr 1fr;gap:60px;align-items:center}h1{font-size:clamp(36px,4.25vw,62px);line-height:1.23;letter-spacing:-3px;margin:0 0 25px;font-weight:800}h1 .accent{color:var(--teal)}.lede{font-size:17px;color:#536269;line-height:1.9;max-width:570px;margin:0}.cover-links{display:flex;gap:12px;margin-top:30px;flex-wrap:wrap}.primary-link,.secondary-link{padding:10px 17px;border-radius:6px;text-decoration:none;font-size:13px;font-weight:650}.primary-link{background:var(--navy);color:#fff}.secondary-link{border:1px solid #cbd3cd;color:var(--navy)}.cover-meta{display:flex;flex-wrap:wrap;gap:9px 22px;font-size:12px;color:var(--muted);margin-top:36px}.cover-meta strong{color:var(--ink)}
.scenario{background:#fff;border:1px solid #dce4de;border-radius:14px;padding:24px;box-shadow:0 16px 35px rgba(26,58,44,.05)}.scenario-label{display:flex;justify-content:space-between;gap:12px;font-size:10px;color:var(--muted);letter-spacing:1px;border-bottom:1px solid #e8ede8;padding-bottom:14px}.scenario-label span:last-child{color:var(--accent);letter-spacing:0}.scenario h2{font-size:19px;line-height:1.5;letter-spacing:-.5px;margin:20px 0 17px}.signals{display:grid;grid-template-columns:1fr 1fr;gap:10px}.signal{border-radius:8px;background:#edf4ef;padding:13px 14px;font-size:12px;color:var(--teal)}.signal strong{display:block;font-size:17px;margin-top:3px}.signal.problem{background:#fbefe7;color:#a84322}.trace{margin:21px 0 0;padding:0;list-style:none}.trace li{position:relative;padding:0 0 17px 26px;font-size:12px;line-height:1.6;color:var(--muted)}.trace li:before{content:"";position:absolute;left:3px;top:5px;width:7px;height:7px;border-radius:50%;background:#749487}.trace li:not(:last-child):after{content:"";position:absolute;left:6px;top:16px;bottom:1px;width:1px;background:#dce6df}.trace li:last-child{padding-bottom:0}.trace strong{display:block;color:var(--ink);font-size:13px}.scenario-note{font-size:10px;color:var(--muted);border-top:1px solid #e8ede8;padding-top:12px;margin:18px 0 0}
.thesis{max-width:1240px;margin:0 auto 32px;padding:24px 30px;display:grid;grid-template-columns:160px 1fr;gap:30px;align-items:start;border-top:1px solid #cbd7cd;border-bottom:1px solid #cbd7cd}.thesis .label{font-size:11px;color:var(--teal);font-weight:750;letter-spacing:1px}.thesis p{margin:0;font-size:17px;line-height:1.7;letter-spacing:-.2px}.document-layout{max-width:1330px;margin:0 auto;display:grid;grid-template-columns:235px minmax(0,1fr);gap:50px;padding:15px 45px 80px}.sidebar{position:sticky;top:100px;align-self:start;max-height:calc(100vh - 120px);overflow-y:auto;padding-right:10px;font-size:12px}.sidebar-title{font-size:10px;letter-spacing:1.7px;color:#74827a;margin:8px 0 16px}.toc a{display:flex;gap:10px;text-decoration:none;padding:9px 10px;color:#65726c;border-left:2px solid transparent;line-height:1.5;border-radius:0 5px 5px 0}.toc a span{font-size:10px;color:#95a198;padding-top:1px;flex-shrink:0}.toc a.active{border-left-color:var(--teal);background:#e9efe8;color:var(--teal);font-weight:700}.toc a:hover{background:#eef1eb}.sidebar-note{margin-top:24px;padding:13px 10px;border-top:1px solid var(--line);font-size:11px;color:var(--muted)}.mobile-toc{display:none}.document{min-width:0}.document-section{margin:0 0 52px;scroll-margin-top:90px}.document-section>h2{font-size:26px;letter-spacing:-.85px;line-height:1.45;padding-bottom:15px;border-bottom:1px solid var(--line);margin:0 0 23px;color:var(--navy)}h3{font-size:18px;letter-spacing:-.4px;margin:31px 0 12px;line-height:1.6}p{font-size:14px;margin:14px 0}strong{font-weight:750}blockquote{margin:20px 0;padding:19px 23px;border-left:3px solid var(--teal);background:#ecf1e9;border-radius:0 8px 8px 0}blockquote p{margin:0 0 13px;font-size:14px}blockquote p:last-child{margin-bottom:0}.document-section:first-child blockquote{margin-top:0;background:white;border:1px solid #dce4de;border-left:3px solid var(--teal)}.document-section:first-child{margin-bottom:42px}ul,ol{font-size:14px;padding-left:23px}li{padding-left:3px;margin:8px 0}.table-wrap{width:100%;overflow-x:auto;border:1px solid #dfe6df;border-radius:8px;margin:20px 0;background:#fff}table{border-collapse:collapse;width:100%;font-size:12px;line-height:1.75;word-break:normal}th,td{text-align:left;padding:12px 14px;vertical-align:top;border-bottom:1px solid #e5ebe5;min-width:110px}th{background:#edf1e9;color:#315447;font-size:11px;font-weight:750}td:first-child{color:#244b41;min-width:115px}tr:last-child td{border-bottom:0}tbody tr:nth-child(even){background:#fafbf8}pre{background:#183536;color:#e2eee6;padding:23px;border-radius:8px;overflow-x:auto;font-size:12px;line-height:1.85;word-break:normal;overflow-wrap:normal}code{font-family:"SFMono-Regular",Consolas,"Liberation Mono",monospace;font-size:.87em}p code,li code,td code{padding:2px 5px;background:#e9eee7;border-radius:3px;color:#345d4d;word-break:break-word}pre code{font-size:inherit}hr{border:0;border-top:1px solid var(--line);margin:30px 0}.doc-footer{border-top:1px solid var(--line);padding:24px 4.5vw;font-size:11px;color:var(--muted);display:flex;justify-content:space-between;gap:20px}.doc-footer a{color:var(--muted)}
@media(min-width:1600px){.cover{padding-top:90px}.document-layout{gap:60px}}
@media(max-width:1100px){.cover{padding:50px 30px}.cover-grid{gap:30px}.document-layout{padding:15px 30px 60px;grid-template-columns:190px minmax(0,1fr);gap:28px}.thesis{margin-left:30px;margin-right:30px}h1{letter-spacing:-2px}.sidebar{font-size:11px}}
@media(max-width:760px){.topbar{height:60px;padding:0 20px}.brand{font-size:19px}.topnav>a{display:none}.print-btn{padding:5px 10px}.cover{padding:35px 20px 30px}.eyebrow{font-size:9px;margin-bottom:18px;letter-spacing:1px}.cover-grid{grid-template-columns:1fr;gap:28px}h1{font-size:40px;letter-spacing:-2px;line-height:1.27}.lede{font-size:15px}.cover-meta{margin-top:23px;font-size:11px;gap:5px 16px}.scenario{padding:20px}.scenario h2{font-size:18px}.thesis{margin:0 20px 24px;padding:20px 0;grid-template-columns:1fr;gap:9px}.thesis p{font-size:15px}.document-layout{display:block;padding:0 20px 40px}.sidebar{display:none}.mobile-toc{display:block;background:#eaf0e8;border:1px solid #d5e0d4;border-radius:7px;margin:0 0 25px}.mobile-toc summary{cursor:pointer;font-size:13px;font-weight:650;padding:12px 15px}.mobile-toc .toc{padding:0 10px 12px}.document-section{margin-bottom:40px}.document-section>h2{font-size:23px;letter-spacing:-.8px;margin-bottom:18px}h3{font-size:17px}p,ul,ol{font-size:13px;line-height:1.95}blockquote{padding:15px 17px}blockquote p{font-size:13px}.table-wrap table{min-width:570px}th,td{padding:11px 12px}pre{padding:17px;font-size:11px}.doc-footer{display:block;padding:20px}.doc-footer span{display:block;margin:5px 0}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
@media print{@page{size:A4;margin:16mm 14mm}html{scroll-behavior:auto}body{background:white;color:#17252b;font-size:10pt;-webkit-print-color-adjust:exact;print-color-adjust:exact}.topbar,.sidebar,.mobile-toc,.cover-links,.skip-link{display:none!important}.cover{padding:10px 0 22px;max-width:none}.cover-grid{grid-template-columns:1.15fr 1fr;gap:20px}.eyebrow{margin-bottom:15px;font-size:8pt}h1{font-size:30pt;letter-spacing:-1.5px}.lede{font-size:10pt}.scenario{padding:15px;box-shadow:none}.scenario h2{font-size:13pt}.cover-meta{font-size:8pt;margin-top:15px}.thesis{margin:0 0 25px;padding:14px 0;grid-template-columns:90px 1fr;gap:15px}.thesis p{font-size:11pt}.document-layout{display:block;padding:0}.document-section{margin-bottom:25px}.document-section>h2{font-size:16pt;break-after:avoid}h3{font-size:12pt;break-after:avoid}p,ul,ol,blockquote p{font-size:9pt;line-height:1.7}table{font-size:8pt!important;min-width:0!important}th,td{padding:7px;min-width:0;overflow-wrap:anywhere}.table-wrap{overflow:visible;border-radius:0}thead{display:table-header-group}tr{break-inside:avoid}blockquote,pre,.scenario{break-inside:avoid}pre{font-size:8pt;white-space:pre-wrap}a{color:inherit;text-decoration:none}.doc-footer{padding:15px 0}.trace li{font-size:8pt}.trace strong{font-size:9pt}.signal{font-size:8pt}.signal strong{font-size:12pt}}
"""

page = '''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="Aftercare 신규 프로젝트 기획서. 배포 후 확인 업무를 맡는 AI 운영 동료 — AWS Agents for Humans Hackathon.">
<meta name="proposal-source-sha256" content="SOURCE_HASH">
<title>Aftercare — AWS 해커톤 신규 프로젝트 기획서</title><style>CSS</style></head>
<body><a class="skip-link" href="#overview">본문 바로가기</a>
<header class="topbar"><a class="brand" href="#"><span class="brand-mark" aria-hidden="true">a</span>Aftercare</a><nav class="topnav" aria-label="주요 항목"><a href="#section-06">MVP</a><a href="#section-09">데모</a><a href="#section-10">심사 전략</a><a href="#section-11">검증</a><button class="print-btn" type="button" id="print-document">인쇄 / PDF</button></nav></header>
<div class="cover"><div class="eyebrow">AWS AGENTS FOR HUMANS · PROFESSIONAL AGENTS</div>
<div class="cover-grid"><div><h1>배포는 끝났습니다.<br><span class="accent">확인은 맡겨주세요.</span></h1>
<p class="lede">배포 후 30분, 개발자가 반복하는 확인 업무를 맡습니다. 실제 사용자 요청을 살펴보고, 허용된 조치와 재확인까지 이어 가는 AI 운영 동료입니다.</p>
<div class="cover-links"><a class="primary-link" href="#section-01">기획 결정 읽기 <span aria-hidden="true">↘</span></a><a class="secondary-link" href="#section-09">5분 데모 계획 <span aria-hidden="true">↗</span></a></div>
<div class="cover-meta"><span><strong>기획 v1.0</strong> · 2026.09.06</span><span><strong>구현 전 · 성과 미측정</strong></span><span>마감 09.15 09:00 KST</span></div></div>
<aside class="scenario" aria-label="핵심 데모의 설계 예시"><div class="scenario-label"><span>THE MOMENT THAT MATTERS</span><span>설계 예시 · 실제 결과 아님</span></div><h2>HTTP는 200.<br>배송비 계산은 틀렸습니다.</h2><div class="signals"><div class="signal">배포 · HTTP 응답<strong>성공 · 200</strong></div><div class="signal problem">등록된 기능 검사<strong>예상 결과 불일치</strong></div></div>
<ol class="trace"><li><strong>지금 버전과 이전 버전을 비교</strong>같은 요청의 결과와 로그를 확인합니다.</li><li><strong>허용된 범위에서 실제 조치</strong>변경 충돌을 확인하고 alias를 되돌립니다.</li><li><strong>새로 얻은 표본으로 다시 확인</strong>회복 근거를 남기거나 필요한 판단을 인계합니다.</li></ol><p class="scenario-note">제품 화면을 설명하는 정적 기획 예시입니다. 기능을 실행하는 데모가 아닙니다.</p></aside></div></div>
<div class="thesis"><span class="label">THE PROPOSAL</span><p><strong>한 사람의 반복 업무를 끝까지 맡긴다.</strong><br>문제 발견부터 실제 조치, 결과 확인, 필요한 인계까지 하나의 제품 경험으로 연결합니다.</p></div>
<div class="document-layout"><aside class="sidebar"><div class="sidebar-title">CONTENTS / 14 CHAPTERS</div><nav class="toc" aria-label="기획서 목차">NAV</nav><div class="sidebar-note">편집 원본 <a href="proposal.md">proposal.md</a><br>모든 수치는 근거·예시·목표를 구분합니다. 본 문서는 기획서이며 실행 결과가 아닙니다.</div></aside>
<main class="document"><details class="mobile-toc"><summary>목차 열기 · 14개 항목</summary><nav class="toc" aria-label="모바일 기획서 목차">NAV</nav></details><h2 id="overview" hidden>기획 개요</h2>BODY</main></div>
<footer class="doc-footer"><span>Aftercare · 신규 프로젝트 기획 v1.0 · 2026.09.06</span><span><a href="proposal.md">Markdown 원본</a> · <a href="../proposal-billbuddy-2026-09-04.html">이전 BillBuddy 기획</a></span></footer>
<script>
document.getElementById('print-document').addEventListener('click',()=>window.print());
const sections=[...document.querySelectorAll('.document-section h2')];
const links=[...document.querySelectorAll('.toc a')];
const update=()=>{let current=sections[0]?.id;for(const s of sections){if(s.getBoundingClientRect().top<160)current=s.id;}for(const a of links){const active=a.hash==='#'+current;a.classList.toggle('active',active);if(active)a.setAttribute('aria-current','location');else a.removeAttribute('aria-current');}};
let ticking=false;window.addEventListener('scroll',()=>{if(!ticking){requestAnimationFrame(()=>{update();ticking=false;});ticking=true;}},{passive:true});update();
document.querySelectorAll('.mobile-toc a').forEach(a=>a.addEventListener('click',event=>{event.preventDefault();document.querySelector('.mobile-toc').open=false;requestAnimationFrame(()=>{const target=document.querySelector(a.hash);if(target){history.pushState(null,'',a.hash);window.scrollTo({top:target.getBoundingClientRect().top+window.scrollY-85,behavior:'instant'});update();}});}));
</script></body></html>'''
page = page.replace('SOURCE_HASH', hashlib.sha256(source.encode()).hexdigest()).replace('CSS', css).replace('NAV', nav).replace('BODY', body)
(ROOT / "proposal.html").write_text(page)
print(f"Rendered {len(headings)} sections; {len(page):,} characters; no external runtime dependencies.")
