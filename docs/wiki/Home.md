# Agent Mesh

* * *
<div align="center">
  <img width="280" alt="Agent Mesh" src="https://raw.githubusercontent.com/Soumen2581/Capstone-Project/master/frontend/public/brand/agent-mesh.png" />
</div>

<div align="center">

# Agent Mesh

</div>

<div align="center">
  <b>From one brief to a coordinated specialist team — select, route, execute, synthesise.</b><br/>
  <i>AI-assisted multi-agent orchestration with explainable workflows and shareable results.</i><br/>
  <br/>
  <b>Team 2 — Phoenix</b>
</div>

<br/>

* * *

## Project Description

Agent Mesh is a web-based platform that uses specialised AI agents and an orchestration engine to handle complex, multi-step requests.
For practitioners, researchers, and engineering teams
who submit work too complex for a single model call
the Agent Mesh app
is a web-based application that analyses the brief, activates only the agents that are needed, and runs them in the right order
that provides faster, coordinated, data-driven delivery
unlike traditional multi-model chat tools that broadcast the same prompt to every model and leave coordination to the human
our application improves accessibility and efficiency by deciding what to run, what *not* to run, which model powers each step, and how results are synthesised

### Why this matters
Complex requests such as “audit this code, fix the critical issues, write tests, and produce a report” are **many tasks with dependencies**, not one prompt. Manual prompting is **slow and inconsistent**; fan-out chat tools **multiply cost** without adding control.
Agent Mesh addresses this by offering a scalable, consistent orchestration workflow using capability-driven selection, workflow graphs, and multi-provider routing.

### Target users
Designed for **individuals, researchers, and engineering teams** who need consistent and scalable multi-step AI work with auditability.

### Scope note
Agent Mesh is an **AI-assisted orchestration and research/engineering support tool**, **not a substitute for professional judgment** or regulated clinical/legal decision-making.

### Expected benefits
Improved **consistency**, **scalability**, and reduced **wasted spend** through selective agent activation and transparent cost/routing.

* * *

## Team Members

<table style="width:100%; border-collapse: collapse;">
  <tr>
    <td align="center" valign="top" style="padding: 10px;" colspan="3">
      <img src="https://raw.githubusercontent.com/Soumen2581/Capstone-Project/master/docs/wiki/team/henry-wong.jpg" width="200" height="250" style="object-fit: cover;">
      <br /><b>Henry Wong</b>
      <br />(<a href="mailto:hwong@pace.edu">hwong@pace.edu</a>)
      <br />AI/ML Advisor
    </td>
  </tr>

  <tr>
    <td align="center" valign="top" style="padding: 10px;" colspan="3">
      <img src="https://raw.githubusercontent.com/Soumen2581/Capstone-Project/master/docs/wiki/team/dhwani-dobariya.jpg" width="200" height="250" style="object-fit: cover;">
      <br /><b>Dhwani Dobariya</b>
      <br />(<a href="https://github.com/DhwaniDobariya">DhwaniDobariya</a>)
      <br />Team Leader / Developer
    </td>
  </tr>

  <tr>
    <td align="center" valign="top" style="padding: 10px;">
      <img src="https://raw.githubusercontent.com/Soumen2581/Capstone-Project/master/docs/wiki/team/aniruddha-rath.jpg" width="200" height="250" style="object-fit: cover;">
      <br /><b>Aniruddha Rath</b>
      <br />(<a href="https://github.com/AniRath020697">AniRath020697</a>)
      <br />Developer
    </td>
    <td align="center" valign="top" style="padding: 10px;">
      <img src="https://raw.githubusercontent.com/Soumen2581/Capstone-Project/master/docs/wiki/team/puneet-tulsiani.jpg" width="200" height="250" style="object-fit: cover;">
      <br /><b>Puneet Tulsiani</b>
      <br />(<a href="https://github.com/puneett12">puneett12</a>)
      <br />Developer
    </td>
    <td align="center" valign="top" style="padding: 10px;">
      <img src="https://raw.githubusercontent.com/Soumen2581/Capstone-Project/master/docs/wiki/team/soumen-nageshkar.jpg" width="200" height="250" style="object-fit: cover;">
      <br /><b>Soumen Nageshkar</b>
      <br />(<a href="https://github.com/Soumen2581">Soumen2581</a>)
      <br />Developer
    </td>
  </tr>

  <tr>
    <td align="center" valign="top" style="padding: 10px;">
      <img src="https://raw.githubusercontent.com/Soumen2581/Capstone-Project/master/docs/wiki/team/sutej-kulkarni.jpg" width="200" height="250" style="object-fit: cover;">
      <br /><b>Sutej Kulkarni</b>
      <br />(<a href="https://github.com/Sutej12">Sutej12</a>)
      <br />Developer
    </td>
    <td align="center" valign="top" style="padding: 10px;">
      <img src="https://raw.githubusercontent.com/Soumen2581/Capstone-Project/master/docs/wiki/team/gurjot-singh.jpg" width="200" height="250" style="object-fit: cover;">
      <br /><b>Gurjot Singh</b>
      <br />(<a href="https://github.com/gurjotsingh01">gurjotsingh01</a>)
      <br />Developer
    </td>
    <td align="center" valign="top" style="padding: 10px;">
      <div style="width:200px;height:250px;border:1px dashed #bbb;display:flex;align-items:center;justify-content:center;margin:0 auto;color:#888;">Photo TBD</div>
      <br /><b>Om Jadhav</b>
      <br />(<a href="https://github.com/jadhavom37">jadhavom37</a>)
      <br />Developer
    </td>
  </tr>
</table>

* * *

## Project Design

### High-level architecture (Sprint 0)
Agent Mesh follows an end-to-end modular-monolith pipeline:

- **Frontend (Web UI):** Next.js (App Router) + TypeScript + CSS  
  - Marketing site, `/office` workspace, chat threads, workflow progress, provider settings.
- **Backend API:** Python + FastAPI + JWT / operator identity  
  - Orchestration, agent registry, workflow engine, provider adapters, rate limits.
- **Orchestration / AI layer:** Capability analysis + multi-agent DAG engine  
  - Selects agents, routes models, validates outputs, synthesises a final result.
  - Optional **Level 3 generative teams** design a bespoke team per request.
- **Data Layer:** PostgreSQL + Redis  
  - Durable workflows/results in Postgres; queues, locks, and cache in Redis.

### Core workflow
1. **Brief:** Operator submits a task (or a follow-up in a continuous chat thread) in `/office`.
2. **Analyse:** Capability analysis determines which specialist agents are required (and which are not).
3. **Plan:** A workflow DAG is built (sequence, parallel joins, conditionals / approval gates).
4. **Route:** Each agent is bound to a suitable model/provider (Auto, pinned, Free Only, or generative team).
5. **Execute:** Agents run with retries, skips, hand-offs, and optional human approval.
6. **Synthesise:** Validated outputs are combined into one result shown in the chat thread.
7. **Persist:** Workflow, executions, cost, and conversation history are stored in PostgreSQL.

### MVP (Sprint 1+ direction)
- Web-based interface (product site + `/office`)
- Capability-driven agent selection
- Workflow engine (DAG: sequential / parallel / conditional)
- Multi-provider model routing with fallback
- Continuous chat threads
- Optional generative agent teams (Level 3)
- Docker Compose one-command local run
- Offline demo mode when no API keys are configured

* * *

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
  <img height="48" src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/framer/framer-original.svg" alt="Framer Motion" />
</p>

### Backend
<p>
  <img height="48" src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/fastapi/fastapi-original.svg" alt="FastAPI" />
  <img height="48" src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/sqlalchemy/sqlalchemy-original.svg" alt="SQLAlchemy" />
  <img height="48" src="https://cdn.simpleicons.org/jsonwebtokens" alt="JWT" />
  <img height="48" src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/pytest/pytest-original.svg" alt="pytest" />
</p>

### Orchestration / AI
<p>
  <img height="48" src="https://cdn.simpleicons.org/openai" alt="OpenAI" />
  <img height="48" src="https://cdn.simpleicons.org/anthropic" alt="Anthropic" />
  <img height="48" src="https://cdn.simpleicons.org/googlegemini" alt="Google Gemini" />
  <img height="48" src="https://cdn.simpleicons.org/huggingface" alt="Hugging Face" />
  <img height="48" src="https://raw.githubusercontent.com/Soumen2581/Capstone-Project/master/frontend/public/brand/agent-mesh.png" alt="Agent Mesh" />
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

### Misc. Libraries
<p>
  <img height="48" src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/pytest/pytest-original.svg" alt="pytest" />
  <img height="48" src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/playwright/playwright-original.svg" alt="Playwright" />
  <img height="48" src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/eslint/eslint-original.svg" alt="ESLint" />
  <img height="48" src="https://cdn.simpleicons.org/prettier" alt="Prettier" />
</p>

* * *

# Course Deliverables — Sprint 0

## Presentations (Sprint Reviews)

### Sprint 0
0. [Watch Sprint 0 Presentation Video](https://YOUR-YOUTUBE-LINK) | [Download mp4 File](https://YOUR-FILE-LINK)  
0a. [View Sprint 0 Presentation Slides as PDF](https://YOUR-LINK)  
0b. [Download Sprint 0 Presentation Slides as PowerPoint](https://YOUR-LINK)  
Notes: [universal-office-sprint-0.md](https://github.com/Soumen2581/Capstone-Project/blob/master/docs/sprints/universal-office-sprint-0.md)

---

## Sprint Burndown Charts and Completed Tasks

### Sprint 0
1. [Sprint 0 Completed Tasks](https://YOUR-LINK)

---

## Retrospectives

### Sprint 0
1. [Watch Sprint 0 Retrospective](https://YOUR-YOUTUBE-LINK) | [Download mp4 File](https://YOUR-FILE-LINK)  
Written: [sprint-0.md](https://github.com/Soumen2581/Capstone-Project/blob/master/docs/agile/retrospectives/sprint-0.md)

---

## Team Working Agreement
- [Team Working Agreement as PDF](https://YOUR-LINK) | [Team Working Agreement as Word Document](https://YOUR-LINK)

---

## Diagrams
- [Architecture Diagram](https://YOUR-LINK)
- [Sequence Diagram](https://YOUR-LINK)
- [Context Diagram](https://YOUR-LINK)
- [ER Diagram](https://YOUR-LINK)
- [State Diagram](https://YOUR-LINK)
- [Class Diagram](https://YOUR-LINK)

In-repo architecture write-up: [docs/architecture.md](https://github.com/Soumen2581/Capstone-Project/blob/master/docs/architecture.md)

---

## Source Code (Sprint 0)

- [Frontend](https://github.com/Soumen2581/Capstone-Project/tree/master/frontend)
- [Backend](https://github.com/Soumen2581/Capstone-Project/tree/master/backend)
- [Docs / ADRs / Agile](https://github.com/Soumen2581/Capstone-Project/tree/master/docs)
- **Monorepo:** [https://github.com/Soumen2581/Capstone-Project](https://github.com/Soumen2581/Capstone-Project)

```bash
git clone https://github.com/Soumen2581/Capstone-Project.git
cd Capstone-Project
cp .env.example .env
docker compose up --build
```

| URL | What |
|-----|------|
| http://localhost:3000 | Product site |
| http://localhost:3000/office | Operator workspace |
| http://localhost:8000/docs | API docs |

---

## Clone this wiki locally

```bash
git clone https://github.com/htmw/F2026-T2-Phoenix.wiki.git
```

Paste this file as **Home** when ready to publish on [F2026-T2-Phoenix wiki](https://github.com/htmw/F2026-T2-Phoenix/wiki).
