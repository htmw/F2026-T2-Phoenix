import type { Metadata } from "next";
import type { ReactNode } from "react";
import { DM_Sans, Instrument_Sans } from "next/font/google";

import { BRAND_LOGO_PNG, BRAND_LOGO_SRC, BRAND_NAME } from "@/lib/brand";

import "./globals.css";

const instrument = Instrument_Sans({
  subsets: ["latin"],
  variable: "--font-display-face",
  display: "swap",
});

const dmSans = DM_Sans({
  subsets: ["latin"],
  variable: "--font-body-face",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: `${BRAND_NAME} — AI agents that work as one organization`,
    template: `%s · ${BRAND_NAME}`,
  },
  description: `Describe any goal — market research, a product plan, analysis, or code — and ${BRAND_NAME} assembles a team of AI specialists to deliver it, designing a bespoke team when a task doesn't fit the standing desks. Bring your own model keys. Free AI mode available.`,
  icons: {
    icon: [{ url: BRAND_LOGO_SRC, type: "image/svg+xml" }, { url: BRAND_LOGO_PNG }],
    apple: BRAND_LOGO_PNG,
  },
  openGraph: {
    title: BRAND_NAME,
    description:
      "An operating system for autonomous AI teams, assembled for whatever you're working on.",
    type: "website",
    images: [{ url: BRAND_LOGO_PNG }],
  },
  twitter: {
    card: "summary",
    title: BRAND_NAME,
    description: "AI specialists that assemble into a team for any brief.",
    images: [BRAND_LOGO_PNG],
  },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${instrument.variable} ${dmSans.variable}`}>
      <body>{children}</body>
    </html>
  );
}
