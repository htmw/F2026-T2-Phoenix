/** Marketing-only role archetypes shown on the landing page.
 *
 * These are domain-neutral illustrations of how a team collaborates, not the backend
 * agent ids. The office activates whichever specialists a brief needs, and designs a
 * bespoke team when a task calls for a discipline the standing desks don't cover.
 */

export type OfficeAgentId =
  | "planner"
  | "researcher"
  | "analyst"
  | "builder"
  | "reviewer"
  | "strategist"
  | "synthesizer";

export type OfficeAgent = {
  id: OfficeAgentId;
  name: string;
  role: string;
  blurb: string;
};

export const OFFICE_AGENTS: OfficeAgent[] = [
  {
    id: "planner",
    name: "Planner",
    role: "Shapes the brief",
    blurb: "Breaks the request into the right steps and decides who works on what.",
  },
  {
    id: "researcher",
    name: "Researcher",
    role: "Gathers context",
    blurb: "Finds the facts, sources, and market context the team needs to proceed.",
  },
  {
    id: "analyst",
    name: "Analyst",
    role: "Reads the signals",
    blurb: "Weighs data, risks, and opportunities to sharpen the direction.",
  },
  {
    id: "builder",
    name: "Builder",
    role: "Does the core work",
    blurb: "Produces the substance the brief calls for, a plan, a design, analysis, or code.",
  },
  {
    id: "reviewer",
    name: "Reviewer",
    role: "Quality gate",
    blurb: "Judges the work against the goal and sends it back if it falls short.",
  },
  {
    id: "strategist",
    name: "Strategist",
    role: "Turns findings into moves",
    blurb: "Shapes clear recommendations and a path to act on them.",
  },
  {
    id: "synthesizer",
    name: "Synthesizer",
    role: "Writes the deliverable",
    blurb: "Combines every contribution into one clear, complete result.",
  },
];

export const WORKFLOW_STEPS = [
  "Brief",
  "Plan",
  "Research",
  "Specialists",
  "Review",
  "Synthesize",
  "Deliver",
] as const;

// One connected network: everything feeds the Builder, then flows out to the
// Synthesizer, so no specialist is left floating. Segments are all distinct.
export const COMM_EDGES: { from: OfficeAgentId; to: OfficeAgentId; sample: string }[] = [
  { from: "planner", to: "researcher", sample: "We need competitor pricing before we position." },
  { from: "researcher", to: "builder", sample: "Market size and the top three competitors are in." },
  { from: "analyst", to: "builder", sample: "Demand skews to the 25-34 segment." },
  { from: "builder", to: "reviewer", sample: "First draft of the go-to-market plan is ready." },
  { from: "builder", to: "strategist", sample: "Here's the positioning, what's the launch play?" },
  { from: "reviewer", to: "synthesizer", sample: "Approved, tighten the pricing line in the summary." },
  { from: "strategist", to: "synthesizer", sample: "Recommend a freemium launch in Q2." },
];
