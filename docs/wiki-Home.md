# Agent Mesh
**Team 2 — Phoenix** · AI Agent Orchestration Platform

> From one brief to a coordinated specialist team — select, route, execute, synthesise.

AI-assisted multi-agent orchestration with capability-driven selection, workflow graphs, multi-provider model routing, and an operator workspace (“the mesh”).

**Course wiki:** [https://github.com/htmw/F2026-T2-Phoenix/wiki](https://github.com/htmw/F2026-T2-Phoenix/wiki)

---

## Project Description

**Agent Mesh** (Team 2 — Phoenix) is a web-based platform that uses specialised AI agents and an orchestration engine to handle complex, multi-step requests. For practitioners, researchers, and engineering teams who submit work that is too complex for a single model call, Agent Mesh analyses the brief, activates **only** the agents that are needed, runs them in the right order (sequential, parallel, or conditional), routes each agent to an appropriate model provider, validates outputs, and synthesises one result — unlike traditional multi-model chat tools that broadcast the same prompt to every model and leave coordination to the human.

---

## Why this matters

Complex requests such as “audit this code, fix the critical issues, write tests, and produce a report” are not one task. They are many tasks with dependencies, different skills, and failure modes. Manual prompting is slow and inconsistent; fan-out chat tools multiply cost without adding control.

Agent Mesh addresses this by offering a **scalable, consistent orchestration workflow**: decide what work is required, what is *not* required, in what order it runs, and which model powers each step — with visibility into cost, skips, retries, and approvals.

---

## Target users

Designed for:

- **Individual practitioners** who need multi-step AI work done without manual orchestration  
- **Engineering / research teams** who need repeatable pipelines with auditability  
- **Platform operators** who need to control cost, connect providers, and observe failures  

---

## Scope note

Agent Mesh is an **AI-assisted orchestration and research/engineering support tool**. It coordinates specialised agents and models; it does **not** replace professional judgment, security review sign-off, or clinical/legal decision-making.

---

## Expected benefits

- Improved consistency in how multi-step work is decomposed and executed  
- Lower wasted spend by skipping irrelevant agents and routing by capability/cost  
- Transparency: which agents ran, which were skipped, what each cost, and why  
- Provider flexibility: OpenAI, Anthropic (Claude), Google Gemini, Groq, Hugging Face, and others behind one routing layer  

---

## Team Members

**Team 2 — Phoenix**

| | Name | GitHub | Role |
|---|------|--------|------|
| <img src="https://raw.githubusercontent.com/Soumen2581/Capstone-Project/master/docs/wiki/team/dhwani-dobariya.jpg" width="96" height="96" alt="Dhwani Dobariya" /> | **Dhwani Dobariya** | [DhwaniDobariya](https://github.com/DhwaniDobariya) | Team Leader / Developer |
| <img src="https://raw.githubusercontent.com/Soumen2581/Capstone-Project/master/docs/wiki/team/aniruddha-rath.jpg" width="96" height="96" alt="Aniruddha Rath" /> | **Aniruddha Rath** | [AniRath020697](https://github.com/AniRath020697) | Developer |
| <img src="https://raw.githubusercontent.com/Soumen2581/Capstone-Project/master/docs/wiki/team/soumen-nageshkar.jpg" width="96" height="96" alt="Soumen Nageshkar" /> | **Soumen Nageshkar** | [Soumen2581](https://github.com/Soumen2581) | Developer |
| <img src="https://raw.githubusercontent.com/Soumen2581/Capstone-Project/master/docs/wiki/team/puneet-tulsiani.jpg" width="96" height="96" alt="Puneet Tulsiani" /> | **Puneet Tulsiani** | [puneett12](https://github.com/puneett12) | Developer |
| <img src="https://raw.githubusercontent.com/Soumen2581/Capstone-Project/master/docs/wiki/team/sutej-kulkarni.jpg" width="96" height="96" alt="Sutej Kulkarni" /> | **Sutej Kulkarni** | [Sutej12](https://github.com/Sutej12) | Developer |
| <img src="https://raw.githubusercontent.com/Soumen2581/Capstone-Project/master/docs/wiki/team/gurjot-singh.jpg" width="96" height="96" alt="Gurjot Singh" /> | **Gurjot Singh** | [gurjotsingh01](https://github.com/gurjotsingh01) | Developer |
| | **Om Jadhav** | [jadhavom37](https://github.com/jadhavom37) | Developer |

### Team photos

<p align="center">
  <img src="https://raw.githubusercontent.com/Soumen2581/Capstone-Project/master/docs/wiki/team/dhwani-dobariya.jpg" width="140" alt="Dhwani Dobariya" /><br/>
  <strong>Dhwani Dobariya</strong> — Team Leader
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/Soumen2581/Capstone-Project/master/docs/wiki/team/aniruddha-rath.jpg" width="140" alt="Aniruddha Rath" />
  &nbsp;
  <img src="https://raw.githubusercontent.com/Soumen2581/Capstone-Project/master/docs/wiki/team/puneet-tulsiani.jpg" width="140" alt="Puneet Tulsiani" />
  &nbsp;
  <img src="https://raw.githubusercontent.com/Soumen2581/Capstone-Project/master/docs/wiki/team/soumen-nageshkar.jpg" width="140" alt="Soumen Nageshkar" />
</p>
<p align="center">
  Aniruddha Rath &nbsp;·&nbsp; Puneet Tulsiani &nbsp;·&nbsp; Soumen Nageshkar
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/Soumen2581/Capstone-Project/master/docs/wiki/team/sutej-kulkarni.jpg" width="140" alt="Sutej Kulkarni" />
  &nbsp;
  <img src="https://raw.githubusercontent.com/Soumen2581/Capstone-Project/master/docs/wiki/team/gurjot-singh.jpg" width="140" alt="Gurjot Singh" />
</p>
<p align="center">
  Sutej Kulkarni &nbsp;·&nbsp; Gurjot Singh
</p>

> Add a photo for Om Jadhav when available. Pace emails and refined role titles can be filled in later.

---

## Project Design

### High-level architecture

Agent Mesh follows an end-to-end modular-monolith pipeline:

| Layer | Stack | Responsibility |
|-------|--------|----------------|
| **Frontend (Web UI)** | Next.js (App Router) + TypeScript + CSS | Marketing site, `/office` workspace, chat threads, workflow progress, provider settings |
| **Backend API** | Python + FastAPI + JWT / operator identity | Orchestration, agent registry, workflow engine, provider adapters, rate limits |
| **Data layer** | PostgreSQL + Redis | Durable workflows/results (Postgres); queues, locks, cache (Redis) |
| **Model providers** | External HTTP APIs | OpenAI, Anthropic, Google, Groq, Hugging Face, OpenRouter, etc. |
| **Optional observability** | Prometheus + Grafana | Metrics scrape from `/metrics` |

```
Frontend (Next.js)  →  Backend (FastAPI)  →  AI providers
                             │    │
                      PostgreSQL  Redis
```

Architecture detail: [docs/architecture.md](https://github.com/Soumen2581/Capstone-Project/blob/master/docs/architecture.md)  
ADRs: [docs/adr/](https://github.com/Soumen2581/Capstone-Project/tree/master/docs/adr)

### Core workflow

1. **Brief** — Operator submits a task (or a follow-up in a continuous chat thread) in `/office`.  
2. **Analyse** — Capability analysis determines which specialist agents are required (and which are not).  
3. **Plan** — A workflow DAG is built (sequence, parallel joins, conditionals / approval gates).  
4. **Route** — Each agent is bound to a suitable model/provider (Auto, pinned, Free Only, or generative team).  
5. **Execute** — Agents run with retries, skips, hand-offs, and optional human approval.  
6. **Synthesise** — Validated outputs are combined into one result shown in the chat thread.  
7. **Persist** — Workflow, executions, cost, and conversation thread history are stored in PostgreSQL.

### MVP (demo-ready direction)

- Web UI with product site + `/office` workspace  
- Capability-driven agent selection (not “run every agent”)  
- Workflow engine (DAG: sequential / parallel / conditional)  
- Multi-provider model routing with fallback  
- Continuous chat threads (follow-ups on the same conversation)  
- Optional **Level 3 generative teams** (design a bespoke team per request)  
- Docker Compose one-command local run  
- Offline demo mode when no API keys are configured  

---

## Languages and Tools

### Languages
- TypeScript  
- Python  
- SQL  

### Frontend
- Next.js (App Router)  
- React  
- CSS (design system / Framer Motion on marketing surfaces)  
- Playwright (browser smoke)  

### Backend
- FastAPI  
- Pydantic / SQLAlchemy / Alembic  
- JWT + `X-Operator-Id` operator identity  

### Orchestration / AI
- Multi-agent workflow engine  
- Provider adapters (OpenAI-compatible + Anthropic)  
- Capability analysis + team designer (Level 3)  

### Database & infrastructure
- PostgreSQL  
- Redis  
- Docker / Docker Compose  

### Tools
- GitHub  
- VS Code / Cursor  
- Make (CI-aligned checks)  
- pytest / Vitest-style frontend checks as applicable  

### Misc.
- Prometheus metrics  
- Structured logging  

---

## Final Application Artifacts

> Upload PDFs/videos to the wiki or Google Drive / YouTube, then replace the placeholder links below.

### Live Application
- [Open Live Application](https://YOUR-DEPLOYMENT-URL) *(replace with Vercel / cloud URL when deployed)*  
- Local: `http://localhost:3000` (site) · `http://localhost:3000/office` (workspace) · `http://localhost:8000/docs` (API)

### Final MVP Demo
- [Watch MVP Demo Video (YouTube)](https://YOUR-YOUTUBE-LINK)  
- [Download MVP Demo Video (mp4)](https://YOUR-FILE-LINK)

### Application Manuals
- **User Manual** — [PDF](https://YOUR-LINK) · [Word](https://YOUR-LINK)  
- **Deployment Manual** — [PDF](https://YOUR-LINK) · [Word](https://YOUR-LINK)  
- **API Documentation** — [OpenAPI / Swagger](http://localhost:8000/docs) · [PDF](https://YOUR-LINK)

### Technical Paper
- [View Technical Paper as PDF](https://YOUR-LINK)  
- [Download Technical Paper as Word](https://YOUR-LINK)

---

## Course Deliverables (Sprint Reviews)

> Mirror KneeVision: link presentation video, slides PDF/PPTX, demo, and source for each sprint. Keep filenames consistent on the wiki.

### Sprint 0 — Foundation
- Watch Sprint 0 Presentation Video | Download mp4  
- View Sprint 0 Slides (PDF) | Download PowerPoint  
- Notes: [universal-office-sprint-0.md](https://github.com/Soumen2581/Capstone-Project/blob/master/docs/sprints/universal-office-sprint-0.md)  
- Retro: [sprint-0.md](https://github.com/Soumen2581/Capstone-Project/blob/master/docs/agile/retrospectives/sprint-0.md)

### Sprint 1
- Watch Sprint 1 Presentation Video | Download mp4  
- View Sprint 1 Slides (PDF) | Download PowerPoint  
- Watch Sprint 1 Demo | Download Demo (mp4)  
- Frontend / Backend source: [Capstone-Project](https://github.com/Soumen2581/Capstone-Project)  
- Retro: [sprint-1.md](https://github.com/Soumen2581/Capstone-Project/blob/master/docs/agile/retrospectives/sprint-1.md)

### Sprint 2
- Watch Sprint 2 Presentation Video | Download mp4  
- View Sprint 2 Slides (PDF) | Download PowerPoint  
- Watch Sprint 2 Demo | Download Demo (mp4)  
- Source: [Capstone-Project](https://github.com/Soumen2581/Capstone-Project)  
- Retro: [sprint-2.md](https://github.com/Soumen2581/Capstone-Project/blob/master/docs/agile/retrospectives/sprint-2.md)

### Sprint 3+ / MVP
- Watch Final MVP Demo | Download Final MVP Demo (mp4)  
- MVP Source: [Frontend](https://github.com/Soumen2581/Capstone-Project/tree/master/frontend) · [Backend](https://github.com/Soumen2581/Capstone-Project/tree/master/backend)  
- Product backlog / DoD: [docs/agile/](https://github.com/Soumen2581/Capstone-Project/tree/master/docs/agile)

### Sprint burndown & completed tasks
- Sprint 0 Completed Tasks — *(link)*  
- Sprint 1 Burndown | Completed Tasks — *(link)*  
- Sprint 2 Burndown | Completed Tasks — *(link)*  
- Sprint 3 Burndown | Completed Tasks — *(link)*

### Sprint planning
- Sprint 1 Planning Video | Download  
- Sprint 2 Planning Video | Download  
- Sprint 3 Planning Video | Download  

### Retrospectives
- Sprint 0–8 written retros: [docs/agile/retrospectives/](https://github.com/Soumen2581/Capstone-Project/tree/master/docs/agile/retrospectives)  
- Add presentation recordings here when available  

### Team Working Agreement
- Team Working Agreement (PDF) | (Word) — *(upload & link)*

---

## Diagrams

> Export from draw.io / Lucidchart / Excalidraw and upload images to the wiki (`[[File:architecture.png]]` or Markdown images).

- Architecture Diagram — *(upload)*  
- Sequence Diagram — *(upload)*  
- Context Diagram — *(upload)*  
- ER Diagram — *(upload)*  
- State Diagram (workflow / node statuses) — *(upload)*  
- Class / Module Diagram — *(upload)*  

In-repo architecture write-up: [docs/architecture.md](https://github.com/Soumen2581/Capstone-Project/blob/master/docs/architecture.md)

---

## Additional Project Artifacts

### Product personas
- Individual practitioner  
- Engineering team lead  
- Platform operator  

### Product vision & backlog
- [Product Vision](https://github.com/Soumen2581/Capstone-Project/blob/master/docs/agile/product-vision.md)  
- [Product Backlog](https://github.com/Soumen2581/Capstone-Project/blob/master/docs/agile/product-backlog.md)  
- [Sprint Plan](https://github.com/Soumen2581/Capstone-Project/blob/master/docs/agile/sprint-plan.md)  
- [Definition of Done](https://github.com/Soumen2581/Capstone-Project/blob/master/docs/agile/definition-of-done.md)  
- [Workflow Test Matrix](https://github.com/Soumen2581/Capstone-Project/blob/master/docs/agile/workflow-test-matrix.md)

### User stories & acceptance criteria
- View User Stories & Acceptance Criteria (PDF) | Download Excel — *(upload from Jira/export)*  
- Sprint-wise stories — Sprint 1 / 2 / 3 — *(link)*  

### Application test cases
- Backend: `backend/tests/` (pytest)  
- Continuous chat / generative teams: `test_continuous_chat.py`, `test_generative_teams.py`  
- Frontend smoke: Playwright office smoke  
- Sprint test-case workbooks — *(upload PDF/Excel)*  

### Screenshots
- Product site & office UI: [docs/images/](https://github.com/Soumen2581/Capstone-Project/tree/master/docs/images)

---

## Source Code

### Repository
- **Monorepo:** [https://github.com/Soumen2581/Capstone-Project](https://github.com/Soumen2581/Capstone-Project)

### Final MVP Source Code
- [Frontend Source Code](https://github.com/Soumen2581/Capstone-Project/tree/master/frontend)  
- [Backend Source Code](https://github.com/Soumen2581/Capstone-Project/tree/master/backend)  
- [Docs / ADRs / Agile](https://github.com/Soumen2581/Capstone-Project/tree/master/docs)

### Run locally

```bash
git clone https://github.com/Soumen2581/Capstone-Project.git
cd Capstone-Project
cp .env.example .env
# Optional: add OPENAI_API_KEY / GOOGLE_API_KEY / GROQ_API_KEY / HUGGINGFACE_API_KEY / HF_TOKEN
docker compose up --build
```

| URL | What |
|-----|------|
| http://localhost:3000 | Product site |
| http://localhost:3000/office | Operator workspace |
| http://localhost:8000/docs | API docs |
| http://localhost:8000/healthz | Health |

---

## Clone this wiki locally

```bash
git clone https://github.com/htmw/F2026-T2-Phoenix.wiki.git
```

Paste this page as **Home** on [https://github.com/htmw/F2026-T2-Phoenix/wiki](https://github.com/htmw/F2026-T2-Phoenix/wiki) (or commit `Home.md` in the wiki clone and push).
