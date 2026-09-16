/** Canonical Agent Office specialist names — do not rename. */

export type OfficeAgentId =
  | "planning"
  | "research"
  | "security"
  | "coding"
  | "testing"
  | "review"
  | "documentation";

export type OfficeAgent = {
  id: OfficeAgentId;
  name: string;
  role: string;
  blurb: string;
};

export const OFFICE_AGENTS: OfficeAgent[] = [
  {
    id: "planning",
    name: "Planning",
    role: "Orchestrates the brief",
    blurb: "Breaks work into ordered steps and decides who acts next.",
  },
  {
    id: "research",
    name: "Research",
    role: "Gathers context",
    blurb: "Finds documentation, APIs, and facts the team needs to proceed.",
  },
  {
    id: "security",
    name: "Security",
    role: "Threat awareness",
    blurb: "Looks for vulnerabilities and unsafe patterns before they ship.",
  },
  {
    id: "coding",
    name: "Coding",
    role: "Implements change",
    blurb: "Writes and modifies code against the plan and research.",
  },
  {
    id: "testing",
    name: "Testing",
    role: "Proves it works",
    blurb: "Validates behavior with checks so regressions do not slip through.",
  },
  {
    id: "review",
    name: "Review",
    role: "Quality gate",
    blurb: "Assesses whether work is acceptable and sends it back if not.",
  },
  {
    id: "documentation",
    name: "Documentation",
    role: "Records the outcome",
    blurb: "Captures what changed and why for humans who follow later.",
  },
];

export const WORKFLOW_STEPS = [
  "Task",
  "Planning",
  "Research",
  "Coding",
  "Review",
  "Testing",
  "Result",
] as const;

export const COMM_EDGES: { from: OfficeAgentId; to: OfficeAgentId; sample: string }[] = [
  { from: "research", to: "coding", sample: "Found relevant API documentation." },
  { from: "coding", to: "review", sample: "Adapter implementation ready for review." },
  { from: "review", to: "coding", sample: "Please tighten error handling on timeouts." },
  { from: "testing", to: "coding", sample: "Coverage gap on the failure path." },
  { from: "planning", to: "research", sample: "Need architecture notes before coding." },
  { from: "security", to: "coding", sample: "Avoid logging secrets in this path." },
];
