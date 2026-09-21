# Agent Mesh

<div align="center">
  <img width="320" alt="Agent Mesh" src="https://github.com/Soumen2581/Capstone-Project/raw/master/frontend/public/brand/agent-mesh-logo.png" />
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
      <img src="https://github.com/Soumen2581/Capstone-Project/raw/master/docs/wiki/team/henry-wong.jpg" width="200" height="250" alt="Henry Wong" /><br/>
      <b>Henry Wong</b><br/>
      (<a href="mailto:hwong@pace.edu">hwong@pace.edu</a>)<br/>
      AI/ML Advisor
    </td>
  </tr>
  <tr>
    <td align="center" colspan="3">
      <img src="https://github.com/Soumen2581/Capstone-Project/raw/master/docs/wiki/team/dhwani-dobariya.jpg" width="200" height="250" alt="Dhwani Dobariya" /><br/>
      <b>Dhwani Dobariya</b><br/>
      (<a href="https://github.com/DhwaniDobariya">DhwaniDobariya</a>)<br/>
      Team Leader / Product Owner
    </td>
  </tr>
  <tr>
    <td align="center" width="33%">
      <img src="https://github.com/Soumen2581/Capstone-Project/raw/master/docs/wiki/team/aniruddha-rath.jpg" width="200" height="250" alt="Aniruddha Rath" /><br/>
      <b>Aniruddha Rath</b><br/>
      (<a href="https://github.com/AniRath020697">AniRath020697</a>)<br/>
      Backend Engineer
    </td>
    <td align="center" width="33%">
      <img src="https://github.com/Soumen2581/Capstone-Project/raw/master/docs/wiki/team/puneet-tulsiani.jpg" width="200" height="250" alt="Puneet Tulsiani" /><br/>
      <b>Puneet Tulsiani</b><br/>
      (<a href="https://github.com/puneett12">puneett12</a>)<br/>
      Frontend Engineer
    </td>
    <td align="center" width="33%">
      <img src="https://github.com/Soumen2581/Capstone-Project/raw/master/docs/wiki/team/soumen-nageshkar.jpg" width="200" height="250" alt="Soumen Nageshkar" /><br/>
      <b>Soumen Nageshkar</b><br/>
      (<a href="https://github.com/Soumen2581">Soumen2581</a>)<br/>
      Full-Stack / Platform Engineer
    </td>
  </tr>
  <tr>
    <td align="center" width="33%">
      <img src="https://github.com/Soumen2581/Capstone-Project/raw/master/docs/wiki/team/sutej-kulkarni.jpg" width="200" height="250" alt="Sutej Kulkarni" /><br/>
      <b>Sutej Kulkarni</b><br/>
      (<a href="https://github.com/Sutej12">Sutej12</a>)<br/>
      DevOps / Infrastructure Engineer
    </td>
    <td align="center" width="33%">
      <img src="https://github.com/Soumen2581/Capstone-Project/raw/master/docs/wiki/team/gurjot-singh.jpg" width="200" height="250" alt="Gurjot Singh" /><br/>
      <b>Gurjot Singh</b><br/>
      (<a href="https://github.com/gurjotsingh01">gurjotsingh01</a>)<br/>
      QA / Test Engineer
    </td>
    <td align="center" width="33%">
      <img src="https://github.com/Soumen2581/Capstone-Project/raw/master/docs/wiki/team/om-jadhav.jpg" width="200" height="250" alt="Om Jadhav" /><br/>
      <b>Om Jadhav</b><br/>
      (<a href="https://github.com/jadhavom37">jadhavom37</a>)<br/>
      Documentation & Agile Lead
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
  <img height="48" src="https://github.com/Soumen2581/Capstone-Project/raw/master/frontend/public/brand/agent-mesh-icon.png" alt="Agent Mesh" />
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
- Sprint notes: [universal-office-sprint-0.md](https://github.com/Soumen2581/Capstone-Project/blob/master/docs/sprints/universal-office-sprint-0.md)
- Presentation video / slides (PDF & PPT) — *to be added*

## Sprint Burndown Charts and Completed Tasks

### Sprint 0
- Sprint plan & completed scope: [universal-office-sprint-0.md](https://github.com/Soumen2581/Capstone-Project/blob/master/docs/sprints/universal-office-sprint-0.md)
- Product backlog: [product-backlog.md](https://github.com/Soumen2581/Capstone-Project/blob/master/docs/agile/product-backlog.md)
- Sprint plan overview: [sprint-plan.md](https://github.com/Soumen2581/Capstone-Project/blob/master/docs/agile/sprint-plan.md)
- Burndown chart image — *to be added*

## Retrospectives

### Sprint 0
- Written retrospective: [sprint-0.md](https://github.com/Soumen2581/Capstone-Project/blob/master/docs/agile/retrospectives/sprint-0.md)
- Retrospective video — *to be added*

## Team Working Agreement
- Working agreement: [team-working-agreement.md](https://github.com/Soumen2581/Capstone-Project/blob/master/docs/agile/team-working-agreement.md)
- Signed PDF / Word copies — *to be added*

## Diagrams
- Architecture write-up: [docs/architecture.md](https://github.com/Soumen2581/Capstone-Project/blob/master/docs/architecture.md)
- Conceptual / sequence / class diagram images — *to be added*

## Additional Project Artifacts

### Product Personas

**Persona 1 — Maya (Solo practitioner)**  
Independent researcher who needs multi-step analyses without manually juggling several AI tools. Wants one brief → one coherent result, with clear cost control.

**Persona 2 — Alex (Engineering lead)**  
Leads a small product team. Needs auditable multi-agent workflows (who did what, which model, what failed) for complex tickets like “audit, fix, test, report.”

**Persona 3 — Jordan (Platform / ops engineer)**  
Runs internal tooling. Needs Docker one-command setup, provider key isolation, rate limits, and offline demo mode when keys are unavailable.

### User Stories
- Product backlog / user stories: [product-backlog.md](https://github.com/Soumen2581/Capstone-Project/blob/master/docs/agile/product-backlog.md)

### Acceptance Criteria & Definition of Done
- [definition-of-done.md](https://github.com/Soumen2581/Capstone-Project/blob/master/docs/agile/definition-of-done.md)

### Application Test Cases
- Workflow test matrix: [workflow-test-matrix.md](https://github.com/Soumen2581/Capstone-Project/blob/master/docs/agile/workflow-test-matrix.md)

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
