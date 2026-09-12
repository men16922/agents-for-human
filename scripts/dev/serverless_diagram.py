#!/usr/bin/env python3
"""Portable, editable AWS architecture using official 2026-07-31 AWS SVG icons."""

# ruff: noqa: E501
import base64
import html
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / "submissions/architecture"
ASSETS = ROOT / "assets/architecture/aws"
DEST.mkdir(parents=True, exist_ok=True)
W, H = 1800, 1410
URL = "https://d1u9yhii3gor6j.cloudfront.net"
ICONS = {
    "browser": "Res_Users_48_Light.svg",
    "cdn": "Arch_Amazon-CloudFront_64.svg",
    "api": "Arch_Amazon-API-Gateway_64.svg",
    "lambda": "Arch_AWS-Lambda_64.svg",
    "db": "Arch_Amazon-DynamoDB_64.svg",
    "s3": "Arch_Amazon-Simple-Storage-Service_64.svg",
    "workflow": "Arch_AWS-Step-Functions_64.svg",
    "agent": "Arch_Amazon-Bedrock-AgentCore_64.svg",
    "nova": "Arch_Amazon-Bedrock_64.svg",
    "cloud": "AWS-Cloud-logo_32.svg",
    "region": "Region_32.svg",
}
# Icon and text are independently editable; all icons are embedded for offline portability.
nodes = [
    (
        "browser",
        25,
        250,
        180,
        "browser",
        "Shopper / reviewer",
        ["Request / impact report", "Explicit execution decision"],
    ),
    (
        "cdn",
        285,
        250,
        220,
        "cdn",
        "Amazon CloudFront",
        ["HTTPS distribution", "Static site + /api/*"],
    ),
    ("api", 645, 250, 230, "api", "Amazon API Gateway", ["HTTP API", "Rehearse / report / decide"]),
    (
        "admission",
        1010,
        250,
        250,
        "lambda",
        "AWS Lambda",
        ["Admission + decision API", "Snapshot / recheck / brief"],
    ),
    (
        "control",
        1410,
        250,
        260,
        "db",
        "Amazon DynamoDB",
        ["Control table · on demand", "Source / budget / decisions"],
    ),
    ("site", 645, 445, 230, "s3", "Amazon S3", ["Private React site", "CloudFront origin access"]),
    (
        "workflow",
        1010,
        465,
        250,
        "workflow",
        "AWS Step Functions",
        ["Standard workflow", "Simulate, then finalize report"],
    ),
    (
        "invoke",
        645,
        650,
        230,
        "lambda",
        "AWS Lambda",
        ["Invoke preview Runtime", "IAM-authenticated request"],
    ),
    (
        "snapshot",
        1410,
        650,
        260,
        "s3",
        "Amazon S3",
        ["Immutable source snapshot", "Model cannot overwrite input"],
    ),
    (
        "agent",
        630,
        880,
        260,
        "agent",
        "Bedrock AgentCore",
        [
            "Preview · Strands Agents",
            "Proposal + simulation tools",
            "No commerce invoke permission",
        ],
    ),
    (
        "nova",
        285,
        880,
        220,
        "nova",
        "Amazon Bedrock",
        ["Amazon Nova 2 Lite", "Global inference profile"],
    ),
    (
        "world",
        1010,
        880,
        250,
        "agent",
        "Runtime memory",
        ["12 isolated virtual worlds", "Plan x condition transitions"],
    ),
    (
        "db",
        1410,
        880,
        260,
        "s3",
        "Amazon S3",
        ["Raw simulation artifacts", "Hash-chained event journals"],
    ),
    (
        "finalize",
        1010,
        1140,
        250,
        "lambda",
        "AWS Lambda",
        [
            "Finalize / independent verifier",
            "Stop preview Runtime",
            "Verify 12 cells + settle usage",
        ],
    ),
    (
        "evidence",
        1410,
        1140,
        260,
        "s3",
        "Amazon S3",
        ["Private, versioned evidence", "Impact report + audited evidence"],
    ),
]
edges = [
    ("browser", "cdn", [(205, 282), (285, 282)], "HTTPS"),
    ("cdn", "api", [(505, 282), (645, 282)], "/api/*"),
    ("cdn", "site", [(395, 420), (395, 480), (645, 480)], "static assets / OAC"),
    ("api", "admission", [(875, 282), (1010, 282)], "request"),
    ("admission", "control", [(1260, 282), (1410, 282)], "atomic decision"),
    ("admission", "workflow", [(1135, 420), (1135, 465)], "start"),
    (
        "workflow",
        "invoke",
        [(1010, 520), (935, 520), (935, 625), (760, 625), (760, 650)],
        "",
        [(940, 550)],
    ),
    (
        "admission",
        "snapshot",
        [(1260, 400), (1740, 400), (1740, 610), (1540, 610), (1540, 650)],
        "freeze input",
        [(1640, 565)],
    ),
    ("invoke", "agent", [(760, 820), (760, 880)], "invoke"),
    ("agent", "nova", [(630, 912), (505, 912)], "model calls"),
    ("agent", "world", [(890, 912), (1010, 912)], "simulate"),
    ("world", "db", [(1260, 912), (1410, 912)], "export"),
    (
        "snapshot",
        "world",
        [(1540, 820), (1540, 850), (1135, 850), (1135, 880)],
        "read frozen input",
    ),
    (
        "workflow",
        "finalize",
        [(1135, 635), (1135, 680), (960, 680), (960, 1172), (1010, 1172)],
        "final audit",
        [(967, 710)],
    ),
    (
        "finalize",
        "db",
        [(1260, 1180), (1330, 1180), (1330, 1000), (1410, 1000)],
        "read journal",
        [(1400, 1070)],
    ),
    ("finalize", "evidence", [(1260, 1260), (1410, 1260)], "final audit"),
    (
        "agent",
        "db",
        [(760, 1050), (760, 1095), (1540, 1095), (1540, 1050)],
        "metered runtime evidence",
        [(1135, 1083)],
    ),
]
mx = ET.Element("mxfile", host="app.diagrams.net", type="device", version="24.7.17")
diagram = ET.SubElement(mx, "diagram", id="serverless", name="Deployed architecture")
model = ET.SubElement(
    diagram, "mxGraphModel", page="1", pageWidth=str(W), pageHeight=str(H), grid="1", gridSize="10"
)
root = ET.SubElement(model, "root")
ET.SubElement(root, "mxCell", id="0")
ET.SubElement(root, "mxCell", id="1", parent="0")


def cell(id_, value, x, y, w, h, style):
    c = ET.SubElement(root, "mxCell", id=id_, value=value, style=style, vertex="1", parent="1")
    ET.SubElement(
        c, "mxGeometry", x=str(x), y=str(y), width=str(w), height=str(h), attrib={"as": "geometry"}
    )
    return c


svg = [
    f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}"><defs><marker id="arrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0,0 L7,3.5 L0,7 Z" fill="#596878"/></marker></defs><rect width="100%" height="100%" fill="white"/>'
]


def text(x, y, value, size=16, weight="normal", color="#232f3e", anchor="start"):
    svg.append(
        f'<text x="{x}" y="{y}" font-family="Arial,sans-serif" font-size="{size}" font-weight="{weight}" fill="{color}" text-anchor="{anchor}">{html.escape(value)}</text>'
    )


def label(id_, value, x, y, w, h, size=16, color="#232f3e", bold=False, align="left"):
    cell(
        id_,
        value,
        x,
        y,
        w,
        h,
        f"text;html=1;whiteSpace=wrap;fontSize={size};fontColor={color};fontStyle={int(bold)};align={align};verticalAlign=middle;",
    )
    text(
        x + (w / 2 if align == "center" else 0),
        y + h / 2 + size * 0.35,
        value,
        size,
        "bold" if bold else "normal",
        color,
        "middle" if align == "center" else "start",
    )


def icon(id_, key, x, y, size):
    raw = (ASSETS / ICONS[key]).read_bytes()
    encoded = base64.b64encode(raw).decode()
    cell(
        id_,
        "",
        x,
        y,
        size,
        size,
        "shape=image;verticalLabelPosition=bottom;imageAspect=0;aspect=fixed;image=data:image/svg+xml,"
        + encoded
        + ";",
    )
    svg.append(
        f'<image x="{x}" y="{y}" width="{size}" height="{size}" href="data:image/svg+xml;base64,{encoded}"/>'
    )


def boundary(id_, x, y, w, h, title, key, color, dashed=False):
    cell(
        id_,
        "",
        x,
        y,
        w,
        h,
        f"fillColor=none;strokeColor={color};strokeWidth=2;dashed={int(dashed)};",
    )
    svg.append(
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="none" stroke="{color}" stroke-width="2"'
        + (' stroke-dasharray="7 5"' if dashed else "")
        + "/>"
    )
    icon(id_ + "-icon", key, x + 12, y + 10, 30)
    label(id_ + "-label", title, x + 52, y + 10, w - 80, 30, 16, color, True)


label("title", "Rehearsal | AWS serverless architecture", 40, 28, 1690, 48, 32, bold=True)
label(
    "subtitle",
    "Before external transactions: freeze a plan, measure isolated outcomes, report evidence, then decide.",
    40,
    82,
    1690,
    28,
    18,
    "#596878",
)
boundary("aws-cloud", 245, 135, 1510, 1210, "AWS Cloud", "cloud", "#232f3e")
boundary("region", 580, 185, 1145, 1130, "AWS Region · us-west-2", "region", "#147eba", True)
for i, edge_data in enumerate(edges):
    source, target, points, title, *position = edge_data
    # Pin anchors to the same geometry used by the SVG preview.
    src = next(n for n in nodes if n[0] == source)
    dst = next(n for n in nodes if n[0] == target)
    exit_x = (points[0][0] - src[1]) / src[3]
    exit_y = (points[0][1] - src[2]) / 170
    entry_x = (points[-1][0] - dst[1]) / dst[3]
    entry_y = (points[-1][1] - dst[2]) / 170
    edge = ET.SubElement(
        root,
        "mxCell",
        id=f"edge-{i}",
        value="",
        edge="1",
        parent="1",
        source=source,
        target=target,
        style=f"edgeStyle=none;endArrow=block;endFill=1;strokeColor=#596878;strokeWidth=2;exitX={exit_x};exitY={exit_y};exitPerimeter=0;entryX={entry_x};entryY={entry_y};entryPerimeter=0;",
    )
    geo = ET.SubElement(edge, "mxGeometry", relative="1", attrib={"as": "geometry"})
    arr = ET.SubElement(geo, "Array", attrib={"as": "points"})
    for x, y in points[1:-1]:
        ET.SubElement(arr, "mxPoint", x=str(x), y=str(y))
    svg.append(
        '<polyline points="'
        + " ".join(f"{x},{y}" for x, y in points)
        + '" fill="none" stroke="#596878" stroke-width="2" marker-end="url(#arrow)"/>'
    )
    if title:
        a, b = points[:2]
        x, y = position[0][0] if position else ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2 - 13)
        # Separate text cells keep edge labels stable in diagrams.net.
        label(f"edge-label-{i}", title, x - 80, y - 12, 160, 24, 12, "#596878", align="center")
for id_, x, y, w, key, title, lines in nodes:
    cell(id_, "", x, y, w, 170, "fillColor=none;strokeColor=none;connectable=1;")
    icon(id_ + "-icon", key, x + w / 2 - 32, y, 64)
    label(id_ + "-title", title, x, y + 73, w, 28, 18, bold=True, align="center")
    for i, line in enumerate(lines):
        label(
            id_ + f"-line-{i}",
            line,
            x - 10,
            y + 105 + i * 20,
            w + 20,
            20,
            14,
            "#596878",
            align="center",
        )
label("global-note", "Global edge / inference", 260, 1270, 290, 30, 14, "#596878", align="center")
label(
    "footer",
    URL + "  ·  Deployed 2026-09-12  ·  Synthetic transactions",
    40,
    1360,
    1690,
    25,
    15,
    "#596878",
)
label(
    "footer-cost",
    "Preview path shown; legacy experiment path retained separately. No Amazon connector or real payment authority.",
    40,
    1385,
    1690,
    22,
    13,
    "#596878",
)
svg.append("</svg>")
(DEST / "rehearsal-serverless.svg").write_text("\n".join(svg) + "\n")
# Second editable page makes authority and cost boundaries explicit without cluttering the flow.
diagram = ET.SubElement(mx, "diagram", id="boundaries", name="Authority and cost boundaries")
model = ET.SubElement(diagram, "mxGraphModel", page="1", pageWidth="1520", pageHeight="1000")
root = ET.SubElement(model, "root")
ET.SubElement(root, "mxCell", id="0")
ET.SubElement(root, "mxCell", id="1", parent="0")
cell(
    "title",
    "Authority, evidence and idle cost",
    50,
    25,
    1400,
    60,
    "text;html=1;fontSize=30;fontStyle=1;align=left;",
)
rows = [
    (
        "Public browser",
        "Chooses a fixed request, reads all measured outcomes, then explicitly accepts or declines the plan. No automatic checkout.",
    ),
    (
        "Agent / model",
        "Separate preview role: Bedrock and preview evidence only. No Lambda commerce invocation or commerce-table permissions.",
    ),
    (
        "Isolated simulation",
        "Three frozen supplier plans x four explicit conditions. Each world starts from the same source snapshot with its own state and journal.",
    ),
    (
        "Decision and freshness",
        "A 15-minute report is bound to plan and source hashes. Source revision recheck and decision write are atomic. The export is evidence, not payment authorization.",
    ),
    (
        "Independent verifier",
        "Finalizer stops Runtime, replays journals independently and writes the report outside model-writable S3 prefixes. Incomplete evidence blocks handoff.",
    ),
    (
        "Cost admission",
        "One active run; 40 admissions initially; $4 shared model allowance; $0.50 per AI-run reservation. Unknown provider usage retains its reservation.",
    ),
    (
        "Runtime lifetime",
        "Explicit StopRuntimeSession after each run. Idle timeout 60 seconds; maximum session lifetime 420 seconds. No provisioned runtime concurrency.",
    ),
    (
        "Idle footprint",
        "Private S3 objects, on-demand DynamoDB tables, CloudFront, API and function definitions remain. Stored bytes and requests are metered; no always-on application server.",
    ),
]
for i, (title, body) in enumerate(rows):
    cell(
        "row-" + str(i),
        "<b>" + title + "</b><br><br>" + body,
        50,
        105 + i * 100,
        1400,
        85,
        "rounded=1;whiteSpace=wrap;html=1;align=left;spacing=16;fontSize=16;fillColor="
        + ("#f0f5e8" if i % 2 == 0 else "#f7f9f2")
        + ";strokeColor=#d1ddc5;",
    )
ET.indent(mx)
ET.ElementTree(mx).write(
    DEST / "rehearsal-serverless.drawio", encoding="utf-8", xml_declaration=True
)
print(DEST / "rehearsal-serverless.drawio")
