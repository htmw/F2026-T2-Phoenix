import Link from "next/link";

import { FinalCTA, MarketingFooter } from "@/components/marketing/FinalCTA";
import { HeroSection } from "@/components/marketing/HeroSection";
import { MarketingNav } from "@/components/marketing/MarketingNav";
import {
  CommunicationSection,
  FreeAISection,
  ModelsSection,
  WorkflowSection,
  WorkspaceSection,
} from "@/components/marketing/ProductSections";
import { AgentsSection, IdeaSection } from "@/components/marketing/StorySections";

export default function MarketingPage() {
  return (
    <div className="mkt-root">
      <MarketingNav />
      <main>
        <HeroSection />
        <IdeaSection />
        <AgentsSection />
        <WorkflowSection />
        <CommunicationSection />
        <WorkspaceSection />
        <ModelsSection />
        <FreeAISection />
        <FinalCTA />
      </main>
      <MarketingFooter />
      <div className="mkt-skip-office">
        <Link href="/office">Skip to workspace</Link>
      </div>
    </div>
  );
}
