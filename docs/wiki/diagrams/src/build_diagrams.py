"""Render the wiki diagrams.

SVG diagrams (architecture, context, sequence) are laid out by hand here; the ER,
class and state diagrams are Graphviz sources next to this file. Requires
Graphviz `dot` and `rsvg-convert` on PATH.

    python3 docs/wiki/diagrams/src/build_diagrams.py
"""

from __future__ import annotations

import subprocess
from html import escape
from pathlib import Path

SRC = Path(__file__).resolve().parent
OUT = SRC.parent
FONT = "Helvetica, Arial, sans-serif"
MONO = "Menlo, Consolas, monospace"

INK = "#1f2933"
MUTED = "#52606d"
LINE = "#7b8794"

PALETTE = {
    "presentation": ("#eef0ff", "#4c4fd6"),
    "gateway": ("#e6f6f1", "#0f8a6a"),
    "services": ("#fff5e3", "#c77700"),
    "persistence": ("#fdebef", "#c2255c"),
    "external": ("#f3edff", "#7048e8"),
    "neutral": ("#f5f7fa", "#7b8794"),
}


class Svg:
    def __init__(self, width: int, height: int, title: str) -> None:
        self.w, self.h = width, height
        self.parts: list[str] = []
        self.overlay: list[str] = []
        self.rect(0, 0, width, height, fill="white", stroke="none", rx=0)
        self.rect(0, 0, width, 64, fill="#111827", stroke="none", rx=0)
        self.text(28, 42, title, size=26, weight="bold", fill="white")

    # primitives -------------------------------------------------------------
    def rect(self, x, y, w, h, *, fill="white", stroke=LINE, sw=1.5, rx=8, dash=None, top=False):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        s = (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" '
             f'stroke="{stroke}" stroke-width="{sw}"{d}/>')
        (self.overlay if top else self.parts).append(s)

    def text(self, x, y, s, *, size=14, weight="normal", fill=INK, anchor="start", family=FONT,
             italic=False, top=False):
        style = ' font-style="italic"' if italic else ""
        t = (f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" font-weight="{weight}" '
             f'fill="{fill}" text-anchor="{anchor}"{style}>{escape(s)}</text>')
        (self.overlay if top else self.parts).append(t)

    def label(self, x, y, s, *, size=12, fill=INK, bg="white", anchor="middle", weight="normal"):
        w = len(s) * size * 0.56 + 12
        x0 = x - w / 2 if anchor == "middle" else (x if anchor == "start" else x - w)
        self.rect(x0, y - size - 2, w, size + 9, fill=bg, stroke="none", rx=4, top=True)
        tx = x if anchor == "middle" else (x0 + 6 if anchor == "start" else x - 6)
        self.text(tx, y + 2, s, size=size, fill=fill, anchor=anchor, weight=weight, top=True)

    def box(self, x, y, w, h, title, lines=(), *, kind="neutral", fill=None, title_size=15,
            line_size=12, align="middle", mono_lines=False, sw=1.5, dash=None):
        bg, fg = PALETTE[kind]
        self.rect(x, y, w, h, fill=fill or "white", stroke=fg, sw=sw, dash=dash)
        cx = x + w / 2 if align == "middle" else x + 12
        n = 1 + len(lines)
        block = title_size + (len(lines)) * (line_size + 5)
        ty = y + (h - block) / 2 + title_size - 2
        self.text(cx, ty, title, size=title_size, weight="bold", anchor="middle" if align == "middle" else "start")
        for i, ln in enumerate(lines):
            self.text(cx, ty + (i + 1) * (line_size + 5) + 2, ln, size=line_size, fill=MUTED,
                      anchor="middle" if align == "middle" else "start",
                      family=MONO if mono_lines else FONT)
        return (x, y, w, h)

    def cylinder(self, x, y, w, h, title, lines=(), *, kind="persistence"):
        bg, fg = PALETTE[kind]
        e = 12
        self.parts.append(
            f'<path d="M{x},{y+e} A{w/2},{e} 0 0 0 {x+w},{y+e} L{x+w},{y+h-e} A{w/2},{e} 0 0 1 {x},{y+h-e} Z" '
            f'fill="white" stroke="{fg}" stroke-width="1.6"/>')
        self.parts.append(f'<ellipse cx="{x+w/2}" cy="{y+e}" rx="{w/2}" ry="{e}" fill="{bg}" stroke="{fg}" stroke-width="1.6"/>')
        ty = y + e + (h - e - 16 - len(lines) * 17) / 2 + 16
        self.text(x + w / 2, ty, title, size=15, weight="bold", anchor="middle")
        for i, ln in enumerate(lines):
            self.text(x + w / 2, ty + (i + 1) * 17 + 1, ln, size=12, fill=MUTED, anchor="middle")

    def band(self, x, y, w, h, kind, layer, name, sub):
        bg, fg = PALETTE[kind]
        self.rect(x, y, w, h, fill=bg, stroke=fg, sw=2, rx=10)
        self.rect(x, y, 200, h, fill=fg, stroke=fg, sw=2, rx=10)
        self.rect(x + 190, y, 10, h, fill=fg, stroke="none", rx=0)
        self.text(x + 18, y + 30, layer, size=12, fill="#ffffffcc", weight="bold")
        for i, part in enumerate(name.split("\n")):
            self.text(x + 18, y + 58 + i * 26, part, size=22, weight="bold", fill="white")
        for i, part in enumerate(sub):
            self.text(x + 18, y + 58 + 26 * name.count("\n") + 26 + i * 17, part, size=12, fill="#ffffffdd")

    def group(self, x, y, w, h, title, kind, title_x=None):
        bg, fg = PALETTE[kind]
        self.rect(x, y, w, h, fill="#ffffffaa", stroke=fg, sw=1.4, rx=10, dash="6 4")
        self.text(title_x or x + 14, y + 22, title, size=14, weight="bold", fill=fg)

    def arrow(self, pts, *, color=LINE, sw=1.8, dash=None, label=None, lpos=None, lsize=12,
              head=True, both=False, lfill=None):
        mid = f"m{abs(hash((color, head)))}"
        d = f' stroke-dasharray="{dash}"' if dash else ""
        marker = f' marker-end="url(#{mid})"' if head else ""
        start = f' marker-start="url(#{mid}s)"' if both else ""
        self.parts.append(
            f'<defs><marker id="{mid}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" '
            f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{color}"/></marker>'
            f'<marker id="{mid}s" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" '
            f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{color}"/></marker></defs>')
        path = " ".join(f"{'M' if i == 0 else 'L'}{px},{py}" for i, (px, py) in enumerate(pts))
        self.parts.append(f'<path d="{path}" fill="none" stroke="{color}" stroke-width="{sw}"{d}{marker}{start}/>')
        if label:
            if lpos is None:
                (x1, y1), (x2, y2) = pts[len(pts) // 2 - 1], pts[len(pts) // 2]
                lpos = ((x1 + x2) / 2, (y1 + y2) / 2 + 4)
            self.label(lpos[0], lpos[1], label, size=lsize, fill=lfill or color)

    def save(self, name: str) -> None:
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
               f'viewBox="0 0 {self.w} {self.h}">' + "".join(self.parts) + "".join(self.overlay) + "</svg>")
        path = OUT / f"{name}.svg"
        path.write_text(svg)
        subprocess.run(["rsvg-convert", "-z", "2", "-b", "white", str(path), "-o", str(OUT / f"{name}.png")],
                       check=True)


# ---------------------------------------------------------------------------
# Architecture
# ---------------------------------------------------------------------------
def architecture() -> None:
    s = Svg(2440, 1540, "Agent Mesh — Architecture Diagram")
    L, R = 24, 2000  # layered area
    EX = 2030        # external column

    # Layer 1 — presentation
    s.band(L, 84, R - L, 250, "presentation", "LAYER 1", "Presentation",
           ["Browser · Next.js 16", "App Router · React 19", "TypeScript"])
    s.box(250, 104, 230, 96, "Browser", ["operator opens the", "product site or /office"], kind="presentation")
    s.cylinder(250, 214, 230, 100, "Web storage", ["session token · theme", "chat drafts"], kind="presentation")
    s.group(510, 100, 1050, 220, "Next.js App Router", "presentation")
    s.box(530, 134, 170, 170, "/", ["product site", "marketing pages", "Sign in with Google"], kind="presentation")
    s.box(716, 134, 190, 170, "/office", ["AppShell", "sign-in gate", "theme · account menu"], kind="presentation",
          fill="#f6f7ff")
    tabs = [("Home", ["TaskComposer", "ChatThread", "Conversations"]),
            ("Agents", ["AgentRegistry", "Panel", "enroll form"]),
            ("Work", ["WorkflowProgress", "ActivityFeed", "node controls"]),
            ("Messages", ["MessagesPanel", "AgentDrawer", "mailboxes"]),
            ("Settings", ["SettingsPanel", "provider keys", "routing policy"])]
    for i, (t, ln) in enumerate(tabs):
        s.box(922 + i * 126, 134, 118, 170, t, ln, kind="presentation", title_size=14, line_size=11)
    s.box(1590, 104, 390, 210, "lib/api.ts",
          ["one typed fetch client for every screen", "adds the session bearer token",
           "describeErrorDetail() turns API errors", "into readable messages",
           "polls /workflows/{id} for live progress"], kind="presentation", line_size=13)
    s.arrow([(480, 152), (530, 152)], color="#4c4fd6")
    s.arrow([(365, 200), (365, 214)], color="#4c4fd6", dash="4 3", head=False)
    s.arrow([(700, 219), (716, 219)], color="#4c4fd6")
    s.arrow([(906, 219), (922, 219)], color="#4c4fd6")
    s.arrow([(1552, 219), (1590, 219)], color="#4c4fd6")

    # Layer 2 — API gateway
    s.band(L, 354, R - L, 210, "gateway", "LAYER 2", "API gateway",
           ["FastAPI app", "middleware chain, then", "/api/v1 routers"])
    mws = [("TrustedHost", "production host allow-list"), ("CORS", "browser origins"),
           ("RequestContext", "request id · access log"), ("Operator identity", "session JWT → owner_id"),
           ("Abuse limits", "per-user rate & spend caps")]
    for i, (t, sub) in enumerate(mws):
        x = 250 + i * 262
        s.box(x, 372, 240, 64, t, [sub], kind="gateway")
        if i:
            s.arrow([(x - 22, 404), (x, 404)], color="#0f8a6a")
    s.box(1590, 372, 390, 64, "Probes & scrape", ["/healthz · /readyz · /metrics"], kind="gateway")
    s.box(250, 452, 640, 96, "Platform routers",
          ["auth (/auth/google, /me, /logout) · providers (connect, test, routing-policy)",
           "capabilities · files · metrics · network (messages, memory,",
           "artifacts, decisions, office snapshot)"], kind="gateway", line_size=12)
    s.box(910, 452, 1070, 96, "Orchestration routers",
          ["POST /tasks · POST /tasks/plan · POST /tasks/generative · GET /workflows · GET /workflows/{id}",
           "POST /workflows/{id}/cancel | resume · POST /workflows/{id}/nodes/{key}/approve | reject | retry | skip",
           "agents: GET · POST (enroll) · PATCH (update / disable) · GET /agents/{id}/records"],
          kind="gateway", line_size=12)
    s.arrow([(1785, 314), (1785, 372)], color="#4c4fd6", sw=2.4)
    s.label(1785, 346, "HTTPS JSON + bearer token", fill="#4c4fd6", bg="#e6f6f1")
    s.arrow([(1426, 436), (1426, 452)], color="#0f8a6a")
    s.arrow([(570, 436), (570, 452)], color="#0f8a6a")

    # Layer 3 — application services
    s.band(L, 584, R - L, 520, "services", "LAYER 3", "Application\nservices",
           ["modular monolith —", "one Python process"])
    s.group(240, 600, 650, 488, "Platform services", "services")
    plat = [("Auth service", ["Google ID token → session", "JWT · session_version"]),
            ("Agent enrollment", ["validate schema · unique", "name · create agent table"]),
            ("Provider management", ["encrypted API keys", "model discovery"]),
            ("File generation", ["pdf · docx · xlsx · csv", "artifacts"]),
            ("MetricsService", ["cost · tokens · latency", "Prometheus counters"]),
            ("Collaboration hub", ["messages · memory", "presence · decisions"])]
    pos = {}
    for i, (t, ln) in enumerate(plat):
        x = 258 + (i % 3) * 210
        y = 640 + (i // 3) * 220
        pos[t] = s.box(x, y, 190, 100, t, ln, kind="services", title_size=14)

    s.group(910, 600, 1070, 488, "Orchestration core — one brief → the right agents → one result", "services",
            title_x=1190)
    cw, ch = 236, 96
    cols = [932, 1192, 1452, 1712]
    rows = [640, 790, 940]
    core = {
        "orch": (0, 0, "OrchestrationService", ["prepare · execute · resume", "approve / reject / retry / skip"]),
        "analyser": (1, 0, "CapabilityAnalyser", ["heuristic or LLM", "+ clarification check"]),
        "selector": (2, 0, "AgentSelector", ["minimal covering set", "skip reason per agent"]),
        "planner": (3, 0, "WorkflowPlanner", ["DAG: sequential ·", "parallel · conditional"]),
        "runner": (0, 1, "WorkflowRunner", ["background asyncio", "task per workflow"]),
        "engine": (1, 1, "WorkflowEngine", ["ready nodes · retries", "approvals · feedback"]),
        "executor": (2, 1, "AgentExecutor", ["prompt · call model", "budget check · fallback"]),
        "provreg": (3, 1, "ProviderRegistry", ["rank models by cost,", "latency · route · fallback"]),
        "repo": (0, 2, "WorkflowRepository", ["tasks · workflows · nodes", "executions · results"]),
        "validate": (1, 2, "Output validation", ["JSON Schema per agent", "names the failing field"]),
        "registry": (2, 2, "AgentRegistry", ["database-backed", "capability index"]),
    }
    hot = {"orch", "engine"}
    for k, (c, r, t, ln) in core.items():
        pos[k] = s.box(cols[c], rows[r], cw, ch, t, ln, kind="services", title_size=14,
                       fill="#ffe8c2" if k in hot else None, sw=2 if k in hot else 1.5)
    s.box(1712, 940, cw, ch, "Result synthesis", ["one answer in the", "chat thread"], kind="services",
          title_size=14)
    O = "#c77700"
    mid_y = lambda r: rows[r] + ch / 2
    s.arrow([(cols[0] + cw, mid_y(0)), (cols[1], mid_y(0))], color=O, label="① analyse", lpos=(1180, 676))
    s.arrow([(cols[1] + cw, mid_y(0)), (cols[2], mid_y(0))], color=O, label="② select", lpos=(1440, 676))
    s.arrow([(cols[2] + cw, mid_y(0)), (cols[3], mid_y(0))], color=O, label="③ plan", lpos=(1700, 676))
    s.arrow([(cols[0] + cw / 2, rows[0] + ch), (cols[0] + cw / 2, rows[1])], color=O, label="④ start",
            lpos=(cols[0] + cw / 2, 768))
    s.arrow([(cols[0] + cw, mid_y(1)), (cols[1], mid_y(1))], color=O, label="run()", lpos=(1180, 826))
    s.arrow([(cols[1] + cw, mid_y(1)), (cols[2], mid_y(1))], color=O, label="per node", lpos=(1440, 826))
    s.arrow([(cols[2] + cw, mid_y(1)), (cols[3], mid_y(1))], color=O, label="route", lpos=(1700, 826))
    s.arrow([(cols[1] + 60, rows[1] + ch), (cols[1] + 60, 910), (cols[0] + cw / 2, 910),
             (cols[0] + cw / 2, rows[2])], color=O, label="persist", lpos=(1080, 914))
    s.arrow([(cols[2] + 40, rows[1] + ch), (cols[2] + 40, 920), (cols[1] + cw / 2, 920),
             (cols[1] + cw / 2, rows[2])], color=O, label="validate output", lpos=(1400, 924))
    gx = cols[2] + cw + 12
    s.arrow([(cols[2] + cw, mid_y(0) + 30), (gx, mid_y(0) + 30), (gx, mid_y(2)), (cols[2] + cw, mid_y(2))],
            color=O, dash="5 4")
    s.label(gx, 768, "find_by_capabilities", fill=O, bg="#fffaf0")
    s.arrow([(cols[1] + cw - 20, rows[1] + ch), (cols[1] + cw - 20, 900), (cols[3] + cw / 2, 900),
             (cols[3] + cw / 2, rows[2])], color=O, label="synthesise", lpos=(1840, 904))
    collab = pos["Collaboration hub"]
    s.arrow([(cols[1] + 30, rows[1] + ch), (cols[1] + 30, 1062), (collab[0] + 95, 1062),
             (collab[0] + 95, collab[1] + collab[3])], color=O, dash="5 4", label="lifecycle hooks",
            lpos=(940, 1066))

    # routers → services
    s.arrow([(cols[0] + cw / 2, 548), (cols[0] + cw / 2, rows[0])], color="#0f8a6a", sw=2.4)
    s.label(cols[0] + cw / 2 + 8, 624, "tasks · workflows", fill="#0f8a6a", bg="#fffaf0", anchor="start")
    enr = pos["Agent enrollment"]
    s.arrow([(1700, 548), (1700, 590), (enr[0] + 130, 590), (enr[0] + 130, enr[1])], color="#0f8a6a")
    s.label(enr[0] + 130, 614, "agents (enroll / update)", fill="#0f8a6a", bg="#fffaf0")
    s.arrow([(400, 548), (400, 640)], color="#0f8a6a")

    # Layer 4 — persistence
    s.band(L, 1124, R - L, 330, "persistence", "LAYER 4", "Persistence",
           ["durable state in", "PostgreSQL · ephemeral", "state in Redis"])
    s.cylinder(250, 1160, 220, 150, "Local filesystem", ["generated artifact", "files (pdf, docx, …)"])
    s.rect(500, 1146, 1240, 290, fill="#ffffff", stroke="#c2255c", sw=2.2, rx=14)
    s.text(1120, 1178, "PostgreSQL 17 — single source of truth", size=18, weight="bold", fill="#c2255c",
           anchor="middle")
    groups = [("Registry", ["agents", "agent_capabilities"]),
              ("Workflow & execution", ["tasks · workflows", "workflow_nodes", "workflow_edges",
                                        "executions · agent_results"]),
              ("Identity & providers", ["users · providers · models", "provider_connections",
                                        "routing_policy"]),
              ("Agent network", ["agent_messages", "agent_presence · memories", "artifacts",
                                 "decision_records · network_events"]),
              ("agent_data schema", ["one out_<agent> table", "per enrolled agent,", "columns from its",
                                     "output schema"])]
    for i, (t, ln) in enumerate(groups):
        pos[t] = s.box(518 + i * 244, 1196, 232, 220, t, ln, kind="persistence", mono_lines=True,
                       line_size=12, title_size=14)
    s.cylinder(1770, 1180, 210, 150, "Redis 8", ["rate-limit counters", "locks · cache"])

    P = "#c2255c"
    s.arrow([(cols[0] + cw / 2, rows[2] + ch), (cols[0] + cw / 2, 1120), (pos["Workflow & execution"][0] + 116, 1120),
             (pos["Workflow & execution"][0] + 116, 1196)], color=P, sw=2.2, label="async SQLAlchemy",
            lpos=(cols[0] + cw / 2 - 110, 1116))
    s.arrow([(cols[2] + cw / 2, rows[2] + ch), (cols[2] + cw / 2, 1108), (pos["Registry"][0] + 116, 1108),
             (pos["Registry"][0] + 116, 1196)], color=P)
    s.arrow([(enr[0] + enr[2], 720), (enr[0] + enr[2] + 10, 720), (enr[0] + enr[2] + 10, 1098),
             (pos["agent_data schema"][0] + 116, 1098), (pos["agent_data schema"][0] + 116, 1196)],
            color=P, label="CREATE TABLE agent_data.out_<agent>", lpos=(1530, 1094))
    fg = pos["File generation"]
    s.arrow([(fg[0] + 95, fg[1] + fg[3]), (fg[0] + 95, 1160)], color=P)
    s.arrow([(1500, 436), (1500, 444), (1990, 444), (1990, 1100), (1875, 1100), (1875, 1180)], color=P,
            dash="6 4", label="rate counters", lpos=(1990, 1050))

    # External services
    s.rect(EX, 84, 390, 1370, fill=PALETTE["external"][0], stroke="#7048e8", sw=2, rx=10)
    s.text(EX + 195, 120, "External services", size=20, weight="bold", fill="#7048e8", anchor="middle")
    s.text(EX + 195, 142, "outside the system boundary", size=12, fill=MUTED, anchor="middle")
    s.box(EX + 20, 372, 350, 90, "Prometheus + Grafana", ["scrapes /metrics", "dashboards"], kind="external")
    s.box(EX + 20, 650, 350, 90, "Google Identity", ["Google Sign-In", "ID-token verification"], kind="external")
    s.box(EX + 20, 790, 350, 150, "LLM model providers",
          ["OpenAI · Anthropic · Google Gemini", "DeepSeek · Mistral · Groq · xAI", "OpenRouter · Hugging Face ·",
           "offline FakeProvider (demo mode)"], kind="external")
    V = "#7048e8"
    s.arrow([(EX + 20, 404), (1980, 404)], color=V, dash="6 4", label="scrape", lpos=(2005, 398))
    s.arrow([(cols[3] + cw, mid_y(1)), (EX + 20, mid_y(1))], color=V, sw=2.4, label="completions",
            lpos=(2010, mid_y(1) - 6))
    s.arrow([(300, 640), (300, 572), (2012, 572), (2012, 695), (EX + 20, 695)], color=V)
    s.label(2012, 640, "verify ID token", fill=V)

    # legend
    ly = 1490
    s.text(L, ly, "How to read it", size=14, weight="bold")
    items = [("#4c4fd6", None, "HTTPS from the browser"), ("#0f8a6a", None, "routed request"),
             ("#c77700", None, "in-process call"), ("#c2255c", None, "database / cache / file I/O"),
             ("#7048e8", None, "call to an external service"), (LINE, "6 4", "dependency / optional")]
    for i, (c, d, t) in enumerate(items):
        x = 170 + i * 370
        s.arrow([(x, ly - 5), (x + 60, ly - 5)], color=c, dash=d)
        s.text(x + 72, ly, t, size=13, fill=MUTED)
    s.text(L, ly + 28, "Numbered arrows ①–④ are the order of one task submission.", size=12, fill=MUTED)
    s.save("architecture-diagram")


# ---------------------------------------------------------------------------
# Context diagram (data-flow, level 0)
# ---------------------------------------------------------------------------
def context() -> None:
    s = Svg(2400, 1260, "Agent Mesh — Context Diagram")
    cx, cy, r = 900, 600, 230
    s.rect(330, 100, 1140, 960, fill="#f8f9fc", stroke="#9aa5b1", sw=1.5, rx=18, dash="8 6")
    s.text(350, 128, "System boundary — Agent Mesh (frontend + backend + data stores)", size=13, fill=MUTED)
    s.parts.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="#2b2a8c" stroke="#1b1a5e" stroke-width="3"/>')
    s.text(cx, cy - 52, "PROCESS 0", size=13, fill="#c9c8ff", anchor="middle", weight="bold")
    s.text(cx, cy - 10, "Agent Mesh", size=40, weight="bold", fill="white", anchor="middle")
    for i, ln in enumerate(["turns one brief into a planned,", "validated multi-agent workflow",
                            "and one synthesised result"]):
        s.text(cx, cy + 30 + i * 22, ln, size=16, fill="#e0e0ff", anchor="middle")

    def entity(x, y, w, h, tag, name, sub, kind):
        bg, fg = PALETTE[kind]
        s.rect(x, y, w, h, fill="white", stroke=INK, sw=2.4, rx=2)
        s.text(x + w / 2, y + 30, tag, size=11, fill=fg, anchor="middle", weight="bold")
        s.text(x + w / 2, y + 58, name, size=21, weight="bold", anchor="middle")
        for i, ln in enumerate(sub):
            s.text(x + w / 2, y + 82 + i * 17, ln, size=12, fill=MUTED, anchor="middle")

    entity(40, 340, 260, 180, "PERSON", "Operator",
           ["submits briefs, watches runs", "engineering lead · data analyst", "product manager"], "presentation")
    entity(40, 690, 260, 130, "PERSON", "Platform engineer", ["enrolls and maintains agents"], "gateway")
    entity(1600, 380, 330, 120, "EXTERNAL SYSTEM", "LLM model providers",
           ["OpenAI · Anthropic · Gemini · DeepSeek · …"], "external")
    entity(1600, 540, 330, 100, "EXTERNAL SYSTEM", "Google Identity", ["Google Sign-In / OAuth"], "external")
    entity(1600, 700, 330, 110, "EXTERNAL SYSTEM", "Prometheus + Grafana", ["monitoring dashboards"], "external")

    def store(x, y, did, name, sub):
        s.rect(x, y, 300, 76, fill="white", stroke="#c2255c", sw=2, rx=2)
        s.rect(x, y, 60, 76, fill="#fdebef", stroke="#c2255c", sw=2, rx=2)
        s.text(x + 30, y + 45, did, size=17, weight="bold", fill="#c2255c", anchor="middle")
        s.text(x + 74, y + 33, name, size=16, weight="bold")
        s.text(x + 74, y + 55, sub, size=12, fill=MUTED)

    store(420, 950, "D1", "PostgreSQL 17", "agents · workflows · results · users")
    store(750, 950, "D2", "Redis 8", "rate-limit counters · locks · cache")
    store(1080, 950, "D3", "Artifact files", "generated pdf · docx · xlsx · csv")

    B, G, V, P = "#3b5bdb", "#0f8a6a", "#7048e8", "#c2255c"

    def edge_x(y, side):
        dx = (r * r - (y - cy) ** 2) ** 0.5
        return cx - dx if side == "left" else cx + dx

    def flow(y, fid, text, color, side, inbound):
        ex = 300 if side == "left" else 1600
        circle = edge_x(y, side)
        pts = [(ex, y), (circle, y)] if inbound else [(circle, y), (ex, y)]
        s.arrow(pts, color=color, sw=2)
        mx = (ex + circle) / 2
        w = len(f"{fid}  {text}") * 6.9 + 18
        s.rect(mx - w / 2, y - 12, w, 22, fill="white", stroke=color, sw=1, rx=4, top=True)
        s.rect(mx - w / 2, y - 12, 36, 22, fill=color, stroke="none", rx=4, top=True)
        s.text(mx - w / 2 + 18, y + 4, fid, size=12, weight="bold", fill="white", anchor="middle", top=True)
        s.text(mx - w / 2 + 42, y + 4, text, size=12, fill=color, top=True)

    flow(372, "F1", "brief · follow-up · routing choice", B, "left", True)
    flow(406, "F2", "Google ID token · provider API keys", B, "left", True)
    flow(440, "F3", "approve · reject · retry · skip", B, "left", True)
    flow(474, "F4", "plan · node status · selection reasons", B, "left", False)
    flow(508, "F5", "final result · cost · generated files", B, "left", False)
    flow(730, "F6", "enroll · update · disable agent", G, "left", True)
    flow(780, "F7", "agent id + status, or field error", G, "left", False)
    flow(420, "F8", "prompt + chosen model", V, "right", False)
    flow(468, "F9", "completion · token usage", V, "right", True)
    flow(572, "F10", "ID token to verify", V, "right", False)
    flow(612, "F11", "verified identity", V, "right", True)
    flow(728, "F12", "scrape /metrics", V, "right", True)
    flow(778, "F13", "request · token · cost counters", V, "right", False)

    s.arrow([(760, 790), (560, 950)], color=P, sw=2, both=True)
    s.label(640, 880, "D1  read / write state", fill=P)
    s.arrow([(900, 830), (900, 950)], color=P, sw=2, both=True)
    s.label(900, 900, "D2  incr · TTL", fill=P)
    s.arrow([(1040, 790), (1220, 950)], color=P, sw=2, both=True)
    s.label(1150, 880, "D3  write · stream file", fill=P)

    # data dictionary
    x0, y0 = 1980, 100
    s.rect(x0, y0, 400, 1080, fill="white", stroke="#9aa5b1", sw=1.2, rx=8)
    s.text(x0 + 16, y0 + 30, "Data-flow dictionary", size=16, weight="bold")
    rows = [("F1", "Operator → Agent Mesh", "task brief, follow-up in the same thread, optional model choice"),
            ("F2", "Operator → Agent Mesh", "Google ID token at sign-in; provider API keys in Settings"),
            ("F3", "Operator → Agent Mesh", "node controls on a running workflow"),
            ("F4", "Agent Mesh → Operator", "workflow DAG, node statuses, why each agent was picked or skipped"),
            ("F5", "Agent Mesh → Operator", "synthesised answer, per-step cost, downloadable files"),
            ("F6", "Engineer → Agent Mesh", "name, capabilities, models, input/output schema, cost profile"),
            ("F7", "Agent Mesh → Engineer", "new agent id and Active status, or a 422 naming the field"),
            ("F8", "Agent Mesh → LLM", "system + user prompt, response schema, model"),
            ("F9", "LLM → Agent Mesh", "text, token usage; errors trigger retry / fallback"),
            ("F10", "Agent Mesh → Google", "ID token signature and audience check"),
            ("F11", "Google → Agent Mesh", "verified sub, email, email_verified"),
            ("F12", "Prometheus → Agent Mesh", "periodic GET /metrics"),
            ("F13", "Agent Mesh → Prometheus", "HTTP, token and cost counters"),
            ("D1", "PostgreSQL", "durable state; one agent_data table per agent"),
            ("D2", "Redis", "per-user rate limits and short-lived locks"),
            ("D3", "Files", "artifacts produced by the file-generation service")]
    y = y0 + 64
    for fid, who, what in rows:
        s.text(x0 + 16, y, fid, size=13, weight="bold", fill="#2b2a8c")
        s.text(x0 + 60, y, who, size=13, weight="bold")
        words, line, lines = what.split(), "", []
        for w in words:
            if len(line) + len(w) > 46:
                lines.append(line)
                line = w
            else:
                line = f"{line} {w}".strip()
        lines.append(line)
        for i, ln in enumerate(lines):
            s.text(x0 + 60, y + 18 + i * 16, ln, size=12, fill=MUTED)
        y += 26 + len(lines) * 16 + 8

    ly = 1210
    s.rect(40, ly - 18, 40, 24, fill="white", stroke=INK, sw=2.4, rx=2)
    s.text(92, ly, "external entity", size=13, fill=MUTED)
    s.parts.append(f'<circle cx="270" cy="{ly - 6}" r="13" fill="#2b2a8c"/>')
    s.text(292, ly, "process", size=13, fill=MUTED)
    s.rect(400, ly - 18, 46, 24, fill="#fdebef", stroke="#c2255c", sw=2, rx=2)
    s.text(458, ly, "data store", size=13, fill=MUTED)
    s.arrow([(600, ly - 6), (660, ly - 6)], color=B)
    s.text(672, ly, "data flow — details in the dictionary", size=13, fill=MUTED)
    s.save("context-diagram")


# ---------------------------------------------------------------------------
# Sequence diagram — sign in, submit a brief, run it, watch progress
# ---------------------------------------------------------------------------
def sequence() -> None:
    lanes = [("Operator", "person", "neutral"), ("Office UI", "Next.js /office", "presentation"),
             ("API", "FastAPI routers", "gateway"), ("Orchestration", "Service", "services"),
             ("Analyser +", "Selector", "services"), ("Workflow", "Planner", "services"),
             ("Workflow", "Runner + Engine", "services"), ("Agent", "Executor", "services"),
             ("LLM provider", "via ProviderRegistry", "external"), ("PostgreSQL", "+ agent_data", "persistence"),
             ("Google", "Identity", "external")]
    gap = 200
    x0 = 130
    X = [x0 + i * gap for i in range(len(lanes))]
    W = X[-1] + 130
    steps: list[tuple] = []
    S = steps.append

    S(("phase", "1 · Sign in"))
    S(("msg", 0, 1, "click “Sign in with Google”"))
    S(("msg", 1, 10, "Google Sign-In"))
    S(("ret", 10, 1, "ID token"))
    S(("msg", 1, 2, "POST /api/v1/auth/google {id_token}"))
    S(("msg", 2, 10, "verify signature, audience, expiry"))
    S(("ret", 10, 2, "sub · email · email_verified"))
    S(("msg", 2, 9, "upsert users row"))
    S(("ret", 2, 1, "session JWT"))
    S(("phase", "2 · Submit a brief"))
    S(("msg", 0, 1, "type brief · Start task"))
    S(("self", 1, "empty brief? block and show a hint"))
    S(("msg", 1, 2, "POST /api/v1/tasks {request}"))
    S(("msg", 2, 3, "prepare(request, owner_id)"))
    S(("msg", 3, 4, "analyse(request) + clarity check"))
    S(("open", "alt", "brief is vague", 1, 9))
    S(("ret", 4, 3, "ClarificationNeededError"))
    S(("ret", 2, 1, "422 + clarifying question"))
    S(("else", "a needed capability has no enabled agent"))
    S(("ret", 2, 1, "422 naming the missing capability"))
    S(("else", "brief is clear and every capability is covered"))
    S(("msg", 4, 9, "find_by_capabilities(required)"))
    S(("ret", 4, 3, "SelectionResult: chosen + skip reasons"))
    S(("msg", 3, 5, "plan(request, analysis, selection)"))
    S(("ret", 5, 3, "WorkflowPlan (DAG of nodes + edges)"))
    S(("msg", 3, 9, "insert task, workflow, nodes, edges"))
    S(("msg", 3, 6, "runner.start(prepared)"))
    S(("ret", 2, 1, "201 WorkflowView — nodes + selection reasons"))
    S(("close",))
    S(("phase", "3 · Execute (background task)"))
    S(("open", "loop", "while nodes are waiting or ready", 0, 10))
    S(("self", 6, "find ready nodes · resolve skips"))
    S(("open", "opt", "node requires approval", 0, 9))
    S(("msg", 6, 9, "status → awaiting_approval"))
    S(("msg", 0, 1, "Approve"))
    S(("msg", 1, 2, "POST …/nodes/{key}/approve"))
    S(("msg", 2, 3, "approve_node() → resume"))
    S(("close",))
    S(("open", "par", "each ready node", 5, 10))
    S(("msg", 6, 7, "execute(agent, input, context)"))
    S(("msg", 7, 8, "route + generate(request)"))
    S(("ret", 8, 7, "completion + token usage"))
    S(("self", 7, "validate against output schema"))
    S(("open", "alt", "output is valid", 5, 10))
    S(("ret", 7, 6, "AgentOutput"))
    S(("msg", 6, 9, "execution, result, out_<agent> row"))
    S(("else", "invalid output or provider error"))
    S(("self", 7, "retry up to 3× with backoff, then fallback model"))
    S(("msg", 6, 9, "step Failed with reason · nothing stored"))
    S(("close",))
    S(("close",))
    S(("close",))
    S(("msg", 6, 9, "synthesise final result · workflow completed"))
    S(("phase", "4 · Watch progress"))
    S(("open", "loop", "every few seconds until finished", 1, 9))
    S(("msg", 1, 2, "GET /api/v1/workflows/{id}"))
    S(("msg", 2, 9, "load workflow, nodes, executions"))
    S(("ret", 2, 1, "node statuses · cost · final result"))
    S(("close",))
    S(("self", 1, "show result in the chat thread"))

    step_h = 38
    top = 170
    advance = {"phase": step_h + 16, "open": 30, "else": 40, "close": 12}
    H = top + sum(advance.get(k[0], step_h) for k in steps) + 70
    s = Svg(W, int(H), "Agent Mesh — Sequence Diagram: sign in, submit a brief, run it")

    for i, ((a, b, kind), x) in enumerate(zip(lanes, X)):
        bg, fg = PALETTE[kind]
        s.rect(x - 90, 84, 180, 62, fill=bg, stroke=fg, sw=2, rx=8)
        s.text(x, 110, a, size=15, weight="bold", anchor="middle")
        s.text(x, 130, b, size=12, fill=MUTED, anchor="middle")
        s.arrow([(x, 146), (x, H - 40)], color="#c3cad3", sw=1.4, dash="6 5", head=False)

    y = top
    frames: list[list] = []
    colors = {"alt": "#0f8a6a", "loop": "#3b5bdb", "opt": "#c77700", "par": "#7048e8"}
    for st in steps:
        kind = st[0]
        if kind == "phase":
            y += 8
            s.rect(20, y - 4, W - 40, 30, fill="#fff8db", stroke="#e8c547", sw=1, rx=4)
            s.text(W / 2, y + 16, st[1], size=15, weight="bold", anchor="middle", fill="#7a5d00")
            y += step_h + 8
            continue
        if kind == "open":
            _, op, guard, a, b = st
            frames.append([op, guard, a, b, y, []])
            y += 30
            continue
        if kind == "else":
            frames[-1][5].append((y, st[1]))
            y += 40
            continue
        if kind == "close":
            op, guard, a, b, y1, elses = frames.pop()
            c = colors[op]
            depth = len(frames)
            xl, xr = X[a] - 80 + depth * 8, X[b] + 80 - depth * 8
            s.rect(xl, y1 - 6, xr - xl, y - y1 + 4, fill="none", stroke=c, sw=1.6, rx=4, dash="7 4")
            s.rect(xl, y1 - 6, 52, 22, fill=c, stroke=c, sw=1, rx=3)
            s.text(xl + 26, y1 + 10, op, size=12, weight="bold", fill="white", anchor="middle")
            s.text(xl + 62, y1 + 10, f"[{guard}]", size=12, weight="bold", fill=c)
            for ey, eg in elses:
                s.arrow([(xl, ey + 4), (xr, ey + 4)], color=c, sw=1.2, dash="4 4", head=False)
                s.text(xl + 12, ey + 22, f"[{eg}]", size=12, weight="bold", fill=c)
            y += 12
            continue
        if kind == "self":
            _, a, text = st
            x = X[a]
            s.arrow([(x, y), (x + 34, y), (x + 34, y + 16), (x + 4, y + 16)], color=INK, sw=1.5)
            s.label(x + 44, y + 12, text, anchor="start", size=12)
            y += step_h
            continue
        _, a, b, text = st
        dash = "6 4" if kind == "ret" else None
        xa, xb = X[a], X[b]
        s.arrow([(xa, y + 8), (xb, y + 8)], color=INK if kind == "msg" else MUTED, sw=1.6, dash=dash)
        s.label((xa + xb) / 2, y + 1, text, size=12, fill=INK if kind == "msg" else MUTED)
        y += step_h

    ly = H - 18
    s.arrow([(40, ly - 5), (100, ly - 5)], color=INK)
    s.text(110, ly, "call / request", size=13, fill=MUTED)
    s.arrow([(270, ly - 5), (330, ly - 5)], color=MUTED, dash="6 4")
    s.text(340, ly, "return / response", size=13, fill=MUTED)
    for i, (op, c) in enumerate(colors.items()):
        s.rect(540 + i * 170, ly - 16, 46, 20, fill=c, stroke=c, rx=3)
        s.text(563 + i * 170, ly - 1, op, size=12, weight="bold", fill="white", anchor="middle")
    s.text(540, ly - 1 + 0, "", size=1)
    s.text(1240, ly, "alt = alternatives · loop = repeat · opt = optional · par = in parallel", size=13,
           fill=MUTED)
    s.save("sequence-diagram")


# ---------------------------------------------------------------------------
# Table / class cards shared by the ER and class diagrams
# ---------------------------------------------------------------------------
ROW = 24
HEAD = 36


class Cards:
    def __init__(self, s: Svg) -> None:
        self.s = s
        self.rows: dict[tuple[str, str], tuple[float, float, float]] = {}
        self.boxes: dict[str, tuple[float, float, float, float]] = {}

    def card(self, key, x, y, w, title, rows, color, *, subtitle=None, dashed=False, stereotype=None):
        """rows: (tag, name, type) — tag is PK/FK/(FK)/'' or a UML visibility."""
        s = self.s
        extra = 18 if stereotype else 0
        h = HEAD + extra + sum(10 if r[0] == "---" else ROW for r in rows) + 8
        s.rect(x, y, w, h, fill="white", stroke=color, sw=1.8, rx=6, dash="6 4" if dashed else None)
        s.rect(x, y, w, HEAD + extra, fill=color, stroke=color, sw=1.8, rx=6)
        s.rect(x, y + HEAD + extra - 8, w, 8, fill=color, stroke="none", rx=0)
        if stereotype:
            s.text(x + w / 2, y + 17, stereotype, size=12, fill="#ffffffdd", anchor="middle", italic=True)
        s.text(x + w / 2, y + 24 + extra, title, size=15, weight="bold", fill="white", anchor="middle",
               italic=stereotype in ("«interface»", "«abstract»"))
        if subtitle:
            s.text(x + w - 10, y + 24 + extra, subtitle, size=11, fill="#ffffffcc", anchor="end")
        ry = y + HEAD + extra + 4 - ROW
        for i, (tag, name, typ) in enumerate(rows):
            ry += ROW
            if tag == "---":
                s.arrow([(x, ry + 5), (x + w, ry + 5)], color=color, sw=1.2, head=False)
                ry -= ROW - 10
                continue
            if i % 2 and not stereotype:
                s.rect(x + 1, ry, w - 2, ROW, fill="#f7f8fa", stroke="none", rx=0)
            tag_color = {"PK": "#b7791f", "FK": "#2b6cb0", "(FK)": "#718096"}.get(tag, MUTED)
            s.text(x + 10, ry + 16, tag, size=11, weight="bold", fill=tag_color)
            s.text(x + 58 if tag in ("PK", "FK", "(FK)", "PK·FK") else x + 26, ry + 16, name, size=13,
                   weight="bold" if tag == "PK" else "normal", family=MONO)
            if typ:
                s.text(x + w - 10, ry + 16, typ, size=11, fill="#7b8794", anchor="end", family=MONO)
            self.rows[(key, name.split(" ")[0])] = (x, ry + ROW / 2, w)
        self.boxes[key] = (x, y, w, h)
        return y + h

    def at(self, key, col, side):
        x, y, w = self.rows[(key, col)]
        return (x if side == "left" else x + w, y)


def crow(s: Svg, x, y, direction, color):
    """Crow's-foot 'many' end pointing into a card edge at (x, y)."""
    d = 1 if direction == "right" else -1
    s.parts.append(f'<path d="M{x - 12 * d},{y} L{x},{y - 7} M{x - 12 * d},{y} L{x},{y + 7} '
                   f'M{x - 12 * d},{y} L{x},{y}" stroke="{color}" stroke-width="1.8" fill="none"/>')


def tee(s: Svg, x, y, direction, color):
    d = 1 if direction == "right" else -1
    s.parts.append(f'<path d="M{x + 8 * d},{y - 7} L{x + 8 * d},{y + 7}" stroke="{color}" stroke-width="1.8"/>')


def er() -> None:
    s = Svg(2620, 1510, "Agent Mesh — ER Diagram (PostgreSQL 17)")
    c = Cards(s)
    REG, WF, ID, NET = "#0f8a6a", "#c77700", "#4c4fd6", "#c2255c"
    groups = [(24, 440, "Agent registry — agents are data, not code", "gateway"),
              (452, 880, "Workflow & execution — one DAG per brief", "services"),
              (1346, 440, "Identity & providers", "presentation"),
              (1798, 800, "Agent network — scoped by workflow_id and agent ids", "persistence")]
    for gx, gw, title, kind in groups:
        bg, fg = PALETTE[kind]
        s.rect(gx, 84, gw, 1320, fill=bg, stroke=fg, sw=2, rx=12)
        s.text(gx + 16, 108, title, size=16, weight="bold", fill=fg)

    W = 392
    A, B, C, D, E, F = 48, 476, 916, 1370, 1822, 2206
    y = c.card("agents", A, 160, W, "agents", [
        ("PK", "id", "varchar(64)"), ("", "name  (unique, any case)", "varchar(120)"),
        ("", "description", "text"), ("", "version", "varchar(20)"), ("", "instructions", "text"),
        ("", "input_schema", "jsonb"), ("", "output_schema", "jsonb"), ("", "model_preference", "jsonb"),
        ("", "retry_policy", "jsonb"), ("", "tools · permissions", "jsonb"), ("", "supported_models", "jsonb"),
        ("", "timeout_seconds", "float"), ("", "max_cost_usd", "float"), ("", "enabled", "bool"),
        ("", "table_name", "varchar(63)"), ("", "created_at · updated_at", "timestamptz")], REG)
    y = c.card("agent_capabilities", A, y + 50, W, "agent_capabilities", [
        ("PK", "id", "serial"), ("FK", "agent_id", "→ agents"), ("", "capability  (indexed)", "varchar(64)")], REG)
    c.card("agent_out", A, y + 50, W, "agent_data.out_<agent>", [
        ("PK", "_id", "bigserial"), ("(FK)", "_execution_id", "→ executions"),
        ("(FK)", "_workflow_id", "→ workflows"), ("", "_node_key", "text"), ("", "_payload", "jsonb"),
        ("", "_created_at", "timestamptz"), ("", "<one column per output field>", "text|bigint|double|bool|jsonb")],
        "#3fa585", subtitle="one table per agent", dashed=True)

    y = c.card("tasks", B, 160, W, "tasks", [
        ("PK", "id", "uuid"), ("", "request", "text"), ("", "status", "varchar(20)"), ("", "parameters", "jsonb"),
        ("", "max_cost_usd", "float"), ("", "require_approval", "bool"), ("(FK)", "owner_id", "→ users")], WF)
    y = c.card("workflows", B, y + 50, W, "workflows", [
        ("PK", "id", "uuid"), ("FK", "task_id", "→ tasks"), ("FK", "parent_workflow_id", "→ workflows"),
        ("", "status", "varchar(20)"), ("", "selection", "jsonb"), ("", "total_cost_usd", "float"),
        ("", "final_result", "jsonb"), ("", "error", "text"), ("", "cancel_requested", "bool"),
        ("(FK)", "owner_id", "→ users"), ("", "started_at · completed_at", "timestamptz")], WF)
    c.card("workflow_edges", B, y + 50, W, "workflow_edges", [
        ("PK", "id", "uuid"), ("FK", "workflow_id", "→ workflows"), ("(FK)", "source_key", "→ node_key"),
        ("(FK)", "target_key", "→ node_key"), ("", "condition", "jsonb"), ("", "pass_payload", "bool")], WF)

    y = c.card("workflow_nodes", C, 160, W, "workflow_nodes", [
        ("PK", "id", "uuid"), ("FK", "workflow_id", "→ workflows"), ("", "node_key  (unique per workflow)", "varchar"),
        ("(FK)", "agent_id", "→ agents"), ("", "objective", "text"), ("", "parameters · satisfies", "jsonb"),
        ("", "status", "varchar(24)"), ("", "requires_approval", "bool"), ("", "join_policy", "all | any"),
        ("", "feedback · approval", "jsonb"), ("", "skip_reason", "text"), ("", "result_payload", "jsonb"),
        ("", "attempts · position", "int")], WF)
    y = c.card("executions", C, y + 50, W, "executions", [
        ("PK", "id", "uuid"), ("FK", "node_id", "→ workflow_nodes"), ("", "attempt", "int"),
        ("", "status", "varchar(24)"), ("(FK)", "model_id", "→ models"), ("", "provider_id", "varchar(32)"),
        ("", "input_tokens · output_tokens", "int"), ("", "cost_usd · latency_ms", "float"),
        ("", "error_kind · error_message", "varchar · text"), ("", "started_at · completed_at", "timestamptz")],
        WF, subtitle="one per attempt")
    c.card("agent_results", C, y + 50, W, "agent_results", [
        ("PK", "id", "uuid"), ("FK", "execution_id  (unique)", "→ executions"), ("", "payload", "jsonb"),
        ("", "summary", "text"), ("", "schema_valid", "bool"), ("", "validation_error", "text"),
        ("", "raw_output", "text")], WF)

    y = c.card("users", D, 160, W, "users", [
        ("PK", "google_sub", "varchar(64)"), ("", "email  (unique)", "varchar(320)"), ("", "email_verified", "bool"),
        ("", "display_name", "varchar(240)"), ("", "picture_url", "varchar"), ("", "session_version", "int"),
        ("", "last_login_at", "timestamptz")], ID)
    y = c.card("providers", D, y + 50, W, "providers", [
        ("PK", "id", "varchar(32)"), ("", "name", "varchar(64)"), ("", "enabled", "bool")], ID)
    y = c.card("models", D, y + 50, W, "models", [
        ("PK", "id", "varchar(128)"), ("FK", "provider_id", "→ providers"), ("", "model_name", "varchar(128)"),
        ("", "traits", "jsonb"), ("", "context_tokens · max_output", "int"), ("", "input/output cost per 1M", "float"),
        ("", "typical_latency_ms", "int"), ("", "enabled", "bool")], ID)
    y = c.card("provider_connections", D, y + 50, W, "provider_connections", [
        ("PK·FK", "provider_id", "→ providers"), ("", "encrypted_api_key", "text"), ("", "key_hint", "varchar(8)"),
        ("", "auth_method · status", "varchar"), ("", "last_verified_at", "timestamptz"),
        ("", "last_error", "text"), ("", "discovered_models", "jsonb")], ID)
    c.card("routing_policy", D, y + 50, W, "routing_policy", [
        ("PK", "id  = 'default'", "varchar(32)"), ("", "provider_priority", "jsonb"), ("", "blocked_models", "jsonb")],
        ID, subtitle="single row")

    y = c.card("agent_messages", E, 160, W - 30, "agent_messages", [
        ("PK", "id", "uuid"), ("FK", "parent_id", "→ agent_messages"), ("", "sender_id · recipient_id", "varchar"),
        ("", "type · priority · status", "varchar"), ("", "workflow_id · task_id", "uuid"), ("", "node_key", "varchar"),
        ("", "content · artifact_ids", "jsonb"), ("", "requires_response", "bool"),
        ("", "acknowledged_at · completed_at", "timestamptz")], NET)
    y = c.card("agent_presence", E, y + 50, W - 30, "agent_presence", [
        ("PK", "agent_id", "varchar(64)"), ("", "status · current_task", "varchar · text"),
        ("", "waiting_for · sending_to", "varchar"), ("", "detail", "text"), ("", "updated_at", "timestamptz")], NET)
    c.card("memories", E, y + 50, W - 30, "memories", [
        ("PK", "id", "uuid"), ("", "visibility", "varchar"), ("", "owner_agent_id", "varchar(64)"),
        ("", "operator_id · source_agent_id", "varchar"), ("", "workflow_id", "uuid"), ("", "title", "varchar(240)"),
        ("", "content · tags", "jsonb"), ("", "importance", "float")], NET)
    y = c.card("artifacts", F, 160, W - 30, "artifacts", [
        ("PK", "id", "uuid"), ("", "kind · created_by", "varchar"), ("", "owner_id", "varchar(64)"),
        ("", "workflow_id", "uuid"), ("", "uri", "text"), ("", "content_type · title", "varchar"),
        ("", "extra", "jsonb"), ("", "size_bytes", "int")], NET)
    y = c.card("decision_records", F, y + 50, W - 30, "decision_records", [
        ("PK", "id", "uuid"), ("", "kind · actor_id", "varchar"), ("", "agent_id · node_key", "varchar"),
        ("", "workflow_id", "uuid"), ("", "title · summary", "varchar · text"), ("", "payload · tags", "jsonb"),
        ("", "importance", "float"), ("", "expires_at", "timestamptz")], NET)
    c.card("network_events", F, y + 50, W - 30, "network_events", [
        ("PK", "id", "uuid"), ("", "event_type", "varchar(40)"), ("", "actor_id", "varchar(64)"),
        ("", "workflow_id", "uuid"), ("", "payload", "jsonb"), ("", "created_at", "timestamptz")], NET,
        subtitle="append-only")

    def same_col(a, ac, b, bc, color, label, dx=18, dash=None):
        (x1, y1), (x2, y2) = c.at(a, ac, "left"), c.at(b, bc, "left")
        gx = x1 - dx
        s.arrow([(x1, y1), (gx, y1), (gx, y2), (x2, y2)], color=color, sw=1.8, head=False, dash=dash)
        tee(s, x1, y1, "left", color)
        crow(s, x2, y2, "right", color)
        s.label(gx, (y1 + y2) / 2, label, size=11, fill=color, bg=PALETTE["neutral"][0])

    def across(a, ac, b, bc, color, label, gx, dash=None, many_end=True):
        (x1, y1), (x2, y2) = c.at(a, ac, "right"), c.at(b, bc, "left")
        s.arrow([(x1, y1), (gx, y1), (gx, y2), (x2, y2)], color=color, sw=1.8, head=False, dash=dash)
        tee(s, x1, y1, "right", color)
        if many_end:
            crow(s, x2, y2, "right", color)
        s.label(gx, (y1 + y2) / 2, label, size=11, fill=color)

    same_col("agents", "id", "agent_capabilities", "agent_id", REG, "1 : *")
    same_col("tasks", "id", "workflows", "task_id", WF, "1 : *")
    same_col("workflows", "id", "workflow_edges", "workflow_id", WF, "1 : *")
    same_col("workflows", "id", "workflows", "parent_workflow_id", WF, "follow-up", dx=10)
    across("workflows", "id", "workflow_nodes", "workflow_id", WF, "1 : *", B + W + 24)
    same_col("workflow_nodes", "id", "executions", "node_id", WF, "1 : * attempts")
    same_col("executions", "id", "agent_results", "execution_id", WF, "1 : 0..1")
    same_col("providers", "id", "models", "provider_id", ID, "1 : *")
    same_col("providers", "id", "provider_connections", "provider_id", ID, "1 : 0..1", dx=30)
    same_col("agent_messages", "id", "agent_messages", "parent_id", NET, "reply", dx=10)

    G = "#7b8794"
    (x1, y1) = c.at("models", "id", "left")
    (x2, y2) = c.at("executions", "model_id", "right")
    s.arrow([(x1, y1), (x1 - 24, y1), (x1 - 24, y2), (x2, y2)], color=G, dash="6 4", head=False)
    crow(s, x2, y2, "left", G)
    s.label(x1 - 24, (y1 + y2) / 2, "routed to", size=11, fill=G)

    (x1, y1) = c.at("agents", "id", "right")
    (x2, y2) = c.at("workflow_nodes", "agent_id", "left")
    s.arrow([(x1, y1), (A + W + 14, y1), (A + W + 14, 146), (C - 14, 146), (C - 14, y2), (x2, y2)], color=G,
            dash="6 4", head=False)
    crow(s, x2, y2, "right", G)
    s.label((A + W + C) / 2, 146, "agents.id ← workflow_nodes.agent_id (runs as)", size=11, fill=G)

    (x1, y1) = c.at("executions", "id", "left")
    (x2, y2) = c.at("agent_out", "_execution_id", "right")
    s.arrow([(x1, y1), (C - 8, y1), (C - 8, 1390), (A + W + 8, 1390), (A + W + 8, y2), (x2, y2)], color=G,
            dash="6 4", head=False)
    crow(s, x2, y2, "left", G)
    s.label((A + W + C) / 2, 1390, "valid output → one row in the agent's own table", size=11, fill=G)

    (x1, y1) = c.at("users", "google_sub", "left")
    (x2, y2) = c.at("tasks", "owner_id", "right")
    s.arrow([(x1, y1), (D - 32, y1), (D - 32, 128), (B + W + 12, 128), (B + W + 12, y2), (x2, y2)], color=G,
            dash="6 4", head=False)
    crow(s, x2, y2, "left", G)
    s.label((B + W + D) / 2 + 120, 128, "users.google_sub ← tasks/workflows.owner_id", size=11, fill=G)

    ly = 1470
    s.text(40, ly, "Legend", size=14, weight="bold")
    s.arrow([(120, ly - 5), (190, ly - 5)], color=WF, head=False)
    tee(s, 120, ly - 5, "left", WF)
    crow(s, 190, ly - 5, "right", WF)
    s.text(204, ly, "enforced foreign key (one → many)", size=13, fill=MUTED)
    s.arrow([(480, ly - 5), (550, ly - 5)], color=G, dash="6 4", head=False)
    s.text(564, ly, "logical reference, not enforced", size=13, fill=MUTED)
    s.text(860, ly, "PK primary key · FK foreign key · (FK) logical key · → target table · "
           "all tables except agent_capabilities, agent_presence and network_events also have created_at / updated_at",
           size=13, fill=MUTED)
    s.save("er-diagram")


def rel(s: Svg, pts, kind, color=INK, label=None, lpos=None):
    """UML relationship. kind: assoc · dep · agg · comp · inherit · real."""
    dash = "6 4" if kind in ("dep", "real") else None
    s.arrow(pts, color=color, sw=1.7, dash=dash, head=False)

    def unit(p, q):
        dx, dy = q[0] - p[0], q[1] - p[1]
        n = (dx * dx + dy * dy) ** 0.5 or 1
        return dx / n, dy / n

    ex, ey = pts[-1]
    ux, uy = unit(pts[-2], pts[-1])
    px, py = -uy, ux
    if kind in ("inherit", "real"):
        b = (ex - ux * 16, ey - uy * 16)
        s.parts.append(f'<path d="M{ex},{ey} L{b[0] + px * 9},{b[1] + py * 9} L{b[0] - px * 9},{b[1] - py * 9} Z" '
                       f'fill="white" stroke="{color}" stroke-width="1.7"/>')
    else:
        b = (ex - ux * 13, ey - uy * 13)
        s.parts.append(f'<path d="M{b[0] + px * 7},{b[1] + py * 7} L{ex},{ey} L{b[0] - px * 7},{b[1] - py * 7}" '
                       f'fill="none" stroke="{color}" stroke-width="1.7"/>')
    if kind in ("agg", "comp"):
        sx, sy = pts[0]
        vx, vy = unit(pts[0], pts[1])
        qx, qy = -vy, vx
        m = (sx + vx * 11, sy + vy * 11)
        e = (sx + vx * 22, sy + vy * 22)
        fill = color if kind == "comp" else "white"
        s.parts.append(f'<path d="M{sx},{sy} L{m[0] + qx * 7},{m[1] + qy * 7} L{e[0]},{e[1]} '
                       f'L{m[0] - qx * 7},{m[1] - qy * 7} Z" fill="{fill}" stroke="{color}" stroke-width="1.6"/>')
    if label:
        if lpos is None:
            (x1, y1), (x2, y2) = pts[len(pts) // 2 - 1], pts[len(pts) // 2]
            lpos = ((x1 + x2) / 2, (y1 + y2) / 2 + 4)
        s.label(lpos[0], lpos[1], label, size=11, fill=color)


def class_diagram() -> None:
    s = Svg(2480, 1720, "Agent Mesh — Class Diagram (backend/app)")
    c = Cards(s)
    ORC, ENG, AG, PRV, PER = "#c77700", "#3b4cca", "#0f8a6a", "#7048e8", "#c2255c"
    W = 420
    X = [40, 520, 1000, 1480, 1960]
    gap = 46

    def column(x, items):
        y = 90
        for key, title, color, stereo, rows in items:
            y = c.card(key, x, y, W, title, rows, color, stereotype=stereo) + gap

    column(X[0], [
        ("runner", "WorkflowRunner", ORC, None, [
            ("−", "_tasks", "dict[UUID, asyncio.Task]"), ("---", "", ""),
            ("+", "start(prepared)", "None"), ("+", "start_resume(workflow_id)", "None"),
            ("+", "wait_for(workflow_id, seconds)", "bool"), ("+", "shutdown()", "None")]),
        ("analyser", "CapabilityAnalyser", ORC, "«interface»", [
            ("+", "analyse(request)", "CapabilityAnalysis")]),
        ("heuristic", "HeuristicCapabilityAnalyser", ORC, None, [
            ("+", "analyse(request)", "CapabilityAnalysis"), ("−", "_explain(matched, decomposed)", "str")]),
        ("llmanalyser", "LLMCapabilityAnalyser", ORC, None, [
            ("−", "_providers", "ProviderRegistry"), ("---", "", ""),
            ("+", "analyse(request)", "CapabilityAnalysis"), ("−", "_fall_back(request, reason)", "…")]),
        ("node", "WorkflowNode", ENG, "«schema»", [
            ("+", "key", "str"), ("+", "agent_id", "str"), ("+", "objective", "str"),
            ("+", "satisfies", "tuple[Capability, …]"), ("+", "requires_approval", "bool"),
            ("+", "join_policy", "'all' | 'any'"), ("+", "feedback", "FeedbackRule | None"),
            ("+", "status", "NodeStatus"), ("+", "skip_reason", "str | None")]),
    ])
    column(X[1], [
        ("orch", "OrchestrationService", ORC, None, [
            ("−", "_analyser", "CapabilityAnalyser"), ("−", "_selector", "AgentSelector"),
            ("−", "_planner", "WorkflowPlanner"), ("−", "_engine", "WorkflowEngine"),
            ("−", "_repository", "WorkflowRepository"), ("---", "", ""),
            ("+", "prepare(request, owner_id)", "PreparedWorkflow"), ("+", "execute(prepared)", "WorkflowRun"),
            ("+", "resume(workflow_id)", "OrchestrationResult"), ("+", "approve_node / reject_node", "…"),
            ("+", "retry_node / skip_node", "…"), ("+", "plan_only(request)", "PlanPreviewResult")]),
        ("selector", "AgentSelector", ORC, None, [
            ("−", "_registry", "AgentRegistry"), ("---", "", ""),
            ("+", "select(required, agent_ids)", "SelectionResult")]),
        ("planner", "WorkflowPlanner", ORC, None, [
            ("+", "plan(request, analysis, selection)", "WorkflowPlan"), ("−", "_build_edges(…)", "…")]),
        ("plan", "WorkflowPlan", ENG, "«schema»", [
            ("+", "nodes", "tuple[WorkflowNode, …]"), ("+", "edges", "tuple[WorkflowEdge, …]"),
            ("+", "selection", "AgentSelection | None"), ("---", "", ""),
            ("−", "_validate_graph()", "rejects cycles")]),
        ("edge", "WorkflowEdge", ENG, "«schema»", [
            ("+", "source", "str"), ("+", "target", "str"), ("+", "condition", "EdgeCondition | None"),
            ("+", "pass_payload", "bool")]),
    ])
    column(X[2], [
        ("engine", "WorkflowEngine", ENG, None, [
            ("−", "_registry", "AgentRegistry"), ("−", "_executor", "AgentExecutor"),
            ("−", "_repository", "WorkflowRepository"), ("−", "_collaboration", "Collaboration"),
            ("−", "_max_parallel · _max_repair_cycles", "int"), ("---", "", ""),
            ("+", "run(workflow_id, task_id, plan, budget)", "WorkflowRun"), ("−", "_ready_nodes(plan, state)", "…"),
            ("−", "_resolve_skips(…)", "…"), ("−", "_execute_batch(…)", "…"), ("−", "_route_feedback(…)", "…")]),
        ("run", "WorkflowRun", ENG, "«dataclass»", [
            ("+", "workflow_id", "UUID"), ("+", "status", "WorkflowStatus"),
            ("+", "outputs", "dict[str, AgentOutput]"), ("+", "skipped", "dict[str, str]"),
            ("+", "attempts", "dict[str, int]"), ("+", "total_cost_usd", "float"), ("---", "", ""),
            ("+", "resolved(node_key)", "bool")]),
        ("registry", "AgentRegistry", AG, "«interface»", [
            ("+", "get(agent_id)", "AgentDefinition"), ("+", "list_all(include_disabled)", "list"),
            ("+", "find_by_capabilities(required)", "dict")]),
        ("definition", "AgentDefinition", AG, "«schema»", [
            ("+", "id · name · description", "str"), ("+", "capabilities", "frozenset[Capability]"),
            ("+", "instructions", "str"), ("+", "input_schema · output_schema", "dict"),
            ("+", "model_preference", "ModelPreference"), ("+", "limits · retry_policy", "…"),
            ("+", "enabled", "bool")]),
        ("dbregistry", "DatabaseAgentRegistry", AG, None, [
            ("−", "_session", "AsyncSession"), ("---", "", ""),
            ("+", "set_model_binding(agent_id, model)", "None")]),
    ])
    column(X[3], [
        ("executor", "AgentExecutor", AG, None, [
            ("−", "_providers", "ProviderRegistry"), ("---", "", ""),
            ("+", "execute(agent, input, context)", "AgentOutput"), ("−", "_attempt(agent, input, …)", "…"),
            ("−", "_check_budget(…)", "…"), ("−", "_validate(agent, input, response)", "…")]),
        ("input", "AgentInput", AG, "«schema»", [
            ("+", "task_id", "UUID"), ("+", "node_key · agent_id", "str"), ("+", "objective", "str"),
            ("+", "upstream", "tuple[UpstreamResult, …]"), ("+", "attempt", "int"),
            ("+", "feedback", "str | None")]),
        ("output", "AgentOutput", AG, "«schema»", [
            ("+", "status", "ExecutionStatus"), ("+", "payload", "dict"), ("+", "provider · model", "str"),
            ("+", "routing_reason", "str | None"), ("+", "usage", "TokenUsage"), ("+", "cost_usd · latency_ms", "float"),
            ("+", "error", "ExecutionError | None")]),
        ("repo", "WorkflowRepository", PER, None, [
            ("−", "_session", "AsyncSession"), ("---", "", ""),
            ("+", "create_task(request, owner_id)", "TaskRecord"), ("+", "create_workflow(task_id, plan)", "…"),
            ("+", "record_execution(workflow_id, output)", "…"), ("+", "finish_workflow(…)", "…"),
            ("−", "_store_in_agent_table(…)", "None")]),
        ("collab", "Collaboration", PER, None, [
            ("−", "bus · memory · artifacts · presence", "…"), ("---", "", ""),
            ("+", "on_node_start(…)", "None"), ("+", "on_node_finished(…)", "None"),
            ("+", "on_approval_requested(…)", "None")]),
    ])
    column(X[4], [
        ("provreg", "ProviderRegistry", PRV, None, [
            ("−", "_providers", "dict[str, LLMProvider]"), ("−", "_policy", "RoutingPolicy"), ("---", "", ""),
            ("+", "rank_models(preference)", "list[RoutingDecision]"), ("+", "available_models()", "list[ModelSpec]"),
            ("+", "route(preference)", "RoutingDecision")]),
        ("llm", "LLMProvider", PRV, "«abstract»", [
            ("+", "name", "str"), ("---", "", ""),
            ("+", "generate(request)", "CompletionResponse"), ("+", "stream(request)", "AsyncIterator[str]"),
            ("+", "estimate_cost(request)", "float"), ("+", "validate_configuration()", "None"),
            ("+", "get_model_capabilities()", "tuple[ModelSpec, …]")]),
        ("openai", "OpenAICompatibleProvider", PRV, None, [
            ("+", "base_url", "str"), ("+", "generate(request)", "CompletionResponse"),
            ("", "subclasses: OpenAI · Gemini · DeepSeek · Mistral", ""),
            ("", "Groq · xAI · OpenRouter · Hugging Face · …", "")]),
        ("anthropic", "AnthropicProvider", PRV, None, [("+", "generate(request)", "CompletionResponse")]),
        ("fake", "FakeProvider", PRV, None, [
            ("+", "queue_json(payload)", "None"), ("+", "generate(request)", "CompletionResponse"),
            ("", "offline demo mode and tests", "")]),
    ])

    B = c.boxes

    def mid_r(k, dy=0):
        x, y, w, h = B[k]
        return (x + w, y + 52 + dy)

    def mid_l(k, dy=0):
        x, y, w, h = B[k]
        return (x, y + 52 + dy)

    def top(k, dx=0):
        x, y, w, h = B[k]
        return (x + w / 2 + dx, y)

    def bottom(k, dx=0):
        x, y, w, h = B[k]
        return (x + w / 2 + dx, y + h)

    # top-row wiring
    rel(s, [mid_r("runner"), (X[1], mid_r("runner")[1])], "assoc", ORC, "uses")
    rel(s, [mid_r("orch"), (X[2], mid_r("orch")[1])], "agg", ORC, "_engine")
    rel(s, [mid_r("engine"), (X[3], mid_r("engine")[1])], "agg", ENG, "_executor")
    rel(s, [mid_r("executor"), (X[4], mid_r("executor")[1])], "agg", AG, "_providers")

    # orchestration column
    a = mid_l("orch", 40)
    t = mid_r("analyser", 0)
    rel(s, [a, (496, a[1]), (496, t[1]), t], "agg", ORC, "_analyser", lpos=(496, (a[1] + t[1]) / 2))
    rel(s, [bottom("orch", -60), top("selector", -60)], "agg", ORC, "_selector")
    a = mid_l("orch", 80)
    t = mid_l("planner", 0)
    rel(s, [a, (508, a[1]), (508, t[1]), t], "agg", ORC, "_planner", lpos=(508, (a[1] + t[1]) / 2 + 30))
    rel(s, [bottom("planner"), top("plan")], "dep", ORC, "«creates»")
    rel(s, [bottom("plan"), top("edge")], "comp", ENG, "0..*")
    a = mid_l("plan", 10)
    t = mid_r("node", 10)
    rel(s, [a, (500, a[1]), (500, t[1]), t], "comp", ENG, "1..*", lpos=(500, (a[1] + t[1]) / 2))
    rel(s, [top("heuristic"), bottom("analyser")], "real", ORC)
    a = mid_l("llmanalyser")
    t = mid_l("analyser", 6)
    rel(s, [a, (22, a[1]), (22, t[1]), t], "real", ORC)

    # selector → registry
    a = mid_r("selector")
    t = mid_l("registry")
    rel(s, [a, (980, a[1]), (980, t[1]), t], "assoc", AG, "_registry", lpos=(980, (a[1] + t[1]) / 2))

    # engine column
    rel(s, [bottom("engine"), top("run")], "assoc", ENG, "maintains")
    rel(s, [bottom("registry"), top("definition")], "assoc", AG, "returns")
    a = mid_r("dbregistry")
    t = mid_r("registry", 10)
    rel(s, [a, (1452, a[1]), (1452, t[1]), t], "real", AG)

    a = mid_r("engine", 140)
    t = mid_l("repo")
    rel(s, [a, (1462, a[1]), (1462, t[1]), t], "agg", PER, "_repository", lpos=(1462, t[1] - 40))
    a = mid_r("engine", 170)
    t = mid_l("collab")
    rel(s, [a, (1470, a[1]), (1470, t[1]), t], "agg", PER, "hooks", lpos=(1470, t[1] - 30))

    # executor column
    rel(s, [bottom("executor", -60), top("input", -60)], "dep", AG, "consumes")
    a = bottom("executor", 120)
    t = top("output", 120)
    rel(s, [a, (a[0], B["input"][1] - 10), (X[3] + W + 18, B["input"][1] - 10), (X[3] + W + 18, t[1] - 12),
             (t[0], t[1] - 12), t], "dep", AG, "produces", lpos=(X[3] + W + 18, B["input"][1] + 80))

    # providers column
    rel(s, [bottom("provreg"), top("llm")], "agg", PRV, "1..*")
    rel(s, [top("openai"), bottom("llm")], "inherit", PRV)
    a = mid_r("anthropic", -10)
    t = mid_r("llm", 60)
    rel(s, [a, (2416, a[1]), (2416, t[1]), t], "inherit", PRV)
    a = mid_r("fake", -10)
    rel(s, [a, (2432, a[1]), (2432, t[1] + 14), (t[0], t[1] + 14)], "inherit", PRV)

    # legend
    ly = 1690
    s.text(40, ly, "Notation", size=14, weight="bold")
    items = [("assoc", "association (uses)"), ("agg", "aggregation (injected)"), ("comp", "composition (owns)"),
             ("dep", "dependency"), ("real", "realisation"), ("inherit", "inheritance")]
    for i, (k, t) in enumerate(items):
        x = 150 + i * 300
        rel(s, [(x, ly - 5), (x + 70, ly - 5)], k)
        s.text(x + 82, ly, t, size=13, fill=MUTED)
    s.text(2440, ly, "+ public · − private · «stereotype»", size=13, fill=MUTED, anchor="end")
    s.save("class-diagram")


def graphviz(name: str) -> None:
    src = SRC / f"{name}.dot"
    subprocess.run(["dot", "-Tsvg", str(src), "-o", str(OUT / f"{name}-diagram.svg")], check=True)
    subprocess.run(["dot", "-Tpng", "-Gdpi=170", str(src), "-o", str(OUT / f"{name}-diagram.png")], check=True)


if __name__ == "__main__":
    architecture()
    context()
    sequence()
    er()
    class_diagram()
    graphviz("state")
