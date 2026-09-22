# Agent Mesh

<div align="center">
  <img width="320" alt="Agent Mesh" src="https://github.com/htmw/F2026-T2-Phoenix/raw/main/frontend/public/brand/agent-mesh-logo.png" />
  <br/><br/>
  <b>From one brief to a coordinated specialist team — select, route, execute, synthesise.</b><br/>
  <i>AI-assisted multi-agent orchestration with explainable workflows and shareable results.</i><br/>
  <br/>
  <b>Team 2 — Phoenix</b>
</div>

<br/>

---

## Project Description

Agent Mesh is a web-based platform that uses specialised AI agents and an orchestration engine to handle complex, multi-step requests.
For practitioners, researchers, and engineering teams who submit work too complex for a single model call, the Agent Mesh app analyses the brief, activates only the agents that are needed, and runs them in the right order — providing faster, coordinated, data-driven delivery.
Unlike traditional multi-model chat tools that broadcast the same prompt to every model and leave coordination to the human, Agent Mesh decides what to run, what *not* to run, which model powers each step, and how results are synthesised.

### Why this matters
Complex requests such as “audit this code, fix the critical issues, write tests, and produce a report” are **many tasks with dependencies**, not one prompt. Manual prompting is **slow and inconsistent**; fan-out chat tools **multiply cost** without adding control.
Agent Mesh addresses this with capability-driven selection, workflow graphs, and multi-provider routing.

### Target users
Designed for **individuals, researchers, and engineering teams** who need consistent and scalable multi-step AI work with auditability.

### Scope note
Agent Mesh is an **AI-assisted orchestration and research/engineering support tool**, **not a substitute for professional judgment** or regulated clinical/legal decision-making.

### Expected benefits
Improved **consistency**, **scalability**, and reduced **wasted spend** through selective agent activation and transparent cost/routing.

---

## Team Members

<table>
  <tr>
    <td align="center" colspan="3">
      <img src="https://github.com/htmw/F2026-T2-Phoenix/raw/main/docs/wiki/team/henry-wong.jpg" width="200" height="250" alt="Henry Wong" /><br/>
      <b>Henry Wong</b><br/>
      (<a href="mailto:hwong@pace.edu">hwong@pace.edu</a>)<br/>
      AI/ML Advisor
    </td>
  </tr>
  <tr>
    <td align="center" colspan="3">
      <img src="https://github.com/htmw/F2026-T2-Phoenix/raw/main/docs/wiki/team/dhwani-dobariya.jpg" width="200" height="250" alt="Dhwani Dobariya" /><br/>
      <b>Dhwani Dobariya</b><br/>
      (<a href="https://github.com/DhwaniDobariya">DhwaniDobariya</a>)<br/>
      Team Leader / Product Owner<br/>
      <a href="mailto:dd46109n@pace.edu">dd46109n@pace.edu</a>
    </td>
  </tr>
  <tr>
    <td align="center" width="33%">
      <img src="https://github.com/htmw/F2026-T2-Phoenix/raw/main/docs/wiki/team/aniruddha-rath.jpg" width="200" height="250" alt="Aniruddha Rath" /><br/>
      <b>Aniruddha Rath</b><br/>
      (<a href="https://github.com/AniRath020697">AniRath020697</a>)<br/>
      Backend Engineer<br/>
      <a href="mailto:ar35067n@pace.edu">ar35067n@pace.edu</a>
    </td>
    <td align="center" width="33%">
      <img src="https://github.com/htmw/F2026-T2-Phoenix/raw/main/docs/wiki/team/puneet-tulsiani.jpg" width="200" height="250" alt="Puneet Tulsiani" /><br/>
      <b>Puneet Tulsiani</b><br/>
      (<a href="https://github.com/puneett12">puneett12</a>)<br/>
      Frontend Engineer<br/>
      <a href="mailto:pt00057n@pace.edu">pt00057n@pace.edu</a>
    </td>
    <td align="center" width="33%">
      <img src="https://github.com/htmw/F2026-T2-Phoenix/raw/main/docs/wiki/team/soumen-nageshkar.jpg" width="200" height="250" alt="Soumen Nageshkar" /><br/>
      <b>Soumen Nageshkar</b><br/>
      (<a href="https://github.com/Soumen2581">Soumen2581</a>)<br/>
      Full-Stack / Platform Engineer<br/>
      <a href="mailto:sn92267n@pace.edu">sn92267n@pace.edu</a>
    </td>
  </tr>
  <tr>
    <td align="center" width="33%">
      <img src="https://github.com/htmw/F2026-T2-Phoenix/raw/main/docs/wiki/team/sutej-kulkarni.jpg" width="200" height="250" alt="Sutej Kulkarni" /><br/>
      <b>Sutej Kulkarni</b><br/>
      (<a href="https://github.com/Sutej12">Sutej12</a>)<br/>
      DevOps / Infrastructure Engineer<br/>
      <a href="mailto:sk85676n@pace.edu">sk85676n@pace.edu</a>
    </td>
    <td align="center" width="33%">
      <img src="https://github.com/htmw/F2026-T2-Phoenix/raw/main/docs/wiki/team/gurjot-singh.jpg" width="200" height="250" alt="Gurjot Singh" /><br/>
      <b>Gurjot Singh</b><br/>
      (<a href="https://github.com/gurjotsingh01">gurjotsingh01</a>)<br/>
      QA / Test Engineer<br/>
      <a href="mailto:gs37994n@pace.edu">gs37994n@pace.edu</a>
    </td>
    <td align="center" width="33%">
      <img src="https://github.com/htmw/F2026-T2-Phoenix/raw/main/docs/wiki/team/om-jadhav.jpg" width="200" height="250" alt="Om Jadhav" /><br/>
      <b>Om Jadhav</b><br/>
      (<a href="https://github.com/jadhavom37">jadhavom37</a>)<br/>
      Documentation & Agile Lead<br/>
      <a href="mailto:oj82545n@pace.edu">oj82545n@pace.edu</a>
    </td>
  </tr>
</table>

---

## Project Design

### High-level architecture (Sprint 0)
Agent Mesh follows an end-to-end modular-monolith pipeline:

- **Frontend (Web UI):** Next.js (App Router) + TypeScript + CSS — marketing site, `/office` workspace, chat threads, workflow progress, provider settings
- **Backend API:** Python + FastAPI + JWT / operator identity — orchestration, agent registry, workflow engine, provider adapters, rate limits
- **Orchestration / AI layer:** Capability analysis + multi-agent DAG engine — selects agents, routes models, validates outputs, synthesises a final result; optional Level 3 generative teams
- **Data Layer:** PostgreSQL + Redis — durable workflows/results in Postgres; queues, locks, and cache in Redis

### Core workflow
1. **Brief** — Operator submits a task (or follow-up) in `/office`
2. **Analyse** — Capability analysis determines which specialist agents are required
3. **Plan** — A workflow DAG is built (sequence, parallel joins, conditionals / approval gates)
4. **Route** — Each agent is bound to a suitable model/provider
5. **Execute** — Agents run with retries, skips, hand-offs, and optional human approval
6. **Synthesise** — Validated outputs are combined into one result in the chat thread
7. **Persist** — Workflow, executions, cost, and conversation history are stored in PostgreSQL

### MVP direction
- Web-based interface (product site + `/office`)
- Capability-driven agent selection
- Workflow engine (DAG: sequential / parallel / conditional)
- Multi-provider model routing with fallback
- Continuous chat threads
- Optional generative agent teams (Level 3)
- Docker Compose one-command local run
- Offline demo mode when no API keys are configured

---

## Languages and Tools

### Languages
<p>
  <img height="48" src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/typescript/typescript-original.svg" alt="TypeScript" />
  <img height="48" src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/python/python-original.svg" alt="Python" />
  <img height="48" src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/postgresql/postgresql-original.svg" alt="SQL / PostgreSQL" />
</p>

### Frontend
<p>
  <img height="48" src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/react/react-original.svg" alt="React" />
  <img height="48" src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/nextjs/nextjs-original.svg" alt="Next.js" />
  <img height="48" src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/css3/css3-original.svg" alt="CSS" />
  <img height="48" src="https://cdn.jsdelivr.net/npm/simple-icons@11.15.0/icons/framer.svg" alt="Framer Motion" />
</p>

### Backend
<p>
  <img height="48" src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/fastapi/fastapi-original.svg" alt="FastAPI" />
  <img height="48" src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/sqlalchemy/sqlalchemy-original.svg" alt="SQLAlchemy" />
  <img height="48" src="https://cdn.jsdelivr.net/npm/simple-icons@11.15.0/icons/jsonwebtokens.svg" alt="JWT" />
  <img height="48" src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/pytest/pytest-original.svg" alt="pytest" />
</p>

### Orchestration / AI
<p>
  <img height="48" src="https://cdn.jsdelivr.net/npm/simple-icons@11.15.0/icons/openai.svg" alt="OpenAI" />
  <img height="48" src="https://cdn.jsdelivr.net/npm/simple-icons@11.15.0/icons/anthropic.svg" alt="Anthropic" />
  <img height="48" src="https://cdn.jsdelivr.net/npm/simple-icons@11.15.0/icons/googlegemini.svg" alt="Google Gemini" />
  <img height="48" src="https://huggingface.co/front/assets/huggingface_logo-noborder.svg" alt="Hugging Face" />
  <img height="48" src="https://github.com/htmw/F2026-T2-Phoenix/raw/main/frontend/public/brand/agent-mesh-icon.png" alt="Agent Mesh" />
</p>

### Database & Cloud
<p>
  <img height="48" src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/postgresql/postgresql-original.svg" alt="PostgreSQL" />
  <img height="48" src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/redis/redis-original.svg" alt="Redis" />
  <img height="48" src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/docker/docker-original.svg" alt="Docker" />
</p>

### Tools
<p>
  <img height="48" src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/github/github-original.svg" alt="GitHub" />
  <img height="48" src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/vscode/vscode-original.svg" alt="VS Code" />
  <img height="48" src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/jira/jira-original.svg" alt="Jira" />
  <img height="48" src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/prometheus/prometheus-original.svg" alt="Prometheus" />
</p>

### Testing & Quality
<p>
  <img height="48" src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/pytest/pytest-original.svg" alt="pytest" />
  <img height="48" src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/playwright/playwright-original.svg" alt="Playwright" />
  <img height="48" src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/eslint/eslint-original.svg" alt="ESLint" />
  <img height="48" src="https://cdn.jsdelivr.net/npm/simple-icons@11.15.0/icons/prettier.svg" alt="Prettier" />
</p>

---

# Course Deliverables — Sprint 0

## Presentations (Sprint Reviews)

### Sprint 0
- [Watch deliverable Sprint 0 presentation video](https://www.youtube.com/watch?v=N24yQqrouek)
- [Download deliverable Sprint 0 presentation video](https://drive.google.com/drive/folders/1GBdi5bs3_tnoIBh5kdQvxPU5Wdq4Zfyc)
- [Deliverable presentation slide as PowerPoint](https://github.com/htmw/F2026-T2-Phoenix/blob/main/docs/sprints/AgentMesh_Sprint0_Presentation.pptx)
- [Deliverable presentation slide as PDF](https://github.com/htmw/F2026-T2-Phoenix/blob/main/docs/sprints/AgentMesh_Sprint0_Presentation.pdf)

## Sprint Burndown Charts and Completed Tasks

### Sprint 0
- Sprint notes: [universal-office-sprint-0.md](https://github.com/htmw/F2026-T2-Phoenix/blob/main/docs/sprints/universal-office-sprint-0.md)
- Team Working Agreement (signed PDF): [Teamwork_Agreement_Team2_Phoenix.pdf](https://github.com/htmw/F2026-T2-Phoenix/blob/main/docs/agile/Teamwork_Agreement_Team2_Phoenix.pdf)
- Completed tasks (SCRUM board):

<p align="center">
  <img src="https://github.com/htmw/F2026-T2-Phoenix/raw/main/docs/wiki/sprints/sprint-0-completed-tasks.jpg" alt="Sprint 0 completed tasks — SCRUM-1 through SCRUM-15" width="900" />
</p>

## Retrospectives

### Sprint 0
0a. [Watch Sprint 0 Retrospective Video](https://www.youtube.com/watch?v=OkWZ0Ngln0w) | [Click here to download mp4 File](https://drive.google.com/drive/folders/1GBdi5bs3_tnoIBh5kdQvxPU5Wdq4Zfyc)

## Team Working Agreement
[Team Working Agreement as PDF](https://github.com/htmw/F2026-T2-Phoenix/blob/main/docs/agile/Teamwork_Agreement_Team2_Phoenix.pdf) | [Team Working Agreement (markdown)](https://github.com/htmw/F2026-T2-Phoenix/blob/main/docs/agile/team-working-agreement.md)

## Diagrams
- Architecture write-up: [docs/architecture.md](https://github.com/htmw/F2026-T2-Phoenix/blob/main/docs/architecture.md)

## Additional Project Artifacts

### Product Personas

From Sprint 0 — *Who we're building Agent Mesh for*:

**Priya — Software Engineering Lead**  
**Goal:** A single pipeline that runs security review, code fixes, and tests automatically before merge.  
**Frustration:** Manually chaining separate AI tools for security, coding, and testing is slow and error-prone.

**Daniel — Data Analyst**  
**Goal:** Multi-step analysis — cleaning, analysis, and reporting — done from one plain-language request.  
**Frustration:** General chat models lose track of steps and can't hand structured data cleanly between stages.

**Aisha — Technical Product Manager**  
**Goal:** Visibility into which AI capability ran, why, and what it cost, for every workflow.  
**Frustration:** Black-box chatbot answers make it impossible to audit cost, latency, or decision quality.

## Source Code (Sprint 0)

- [Frontend](https://github.com/htmw/F2026-T2-Phoenix/tree/main/frontend)
- [Backend](https://github.com/htmw/F2026-T2-Phoenix/tree/main/backend)
- [Docs / ADRs / Agile](https://github.com/htmw/F2026-T2-Phoenix/tree/main/docs)
- **Monorepo:** [https://github.com/htmw/F2026-T2-Phoenix](https://github.com/htmw/F2026-T2-Phoenix)

```bash
git clone https://github.com/htmw/F2026-T2-Phoenix.git
cd F2026-T2-Phoenix
cp .env.example .env
docker compose up --build
```

| URL | What |
|-----|------|
| http://localhost:3000 | Product site |
| http://localhost:3000/office | Operator workspace |
| http://localhost:8000/docs | API docs |
