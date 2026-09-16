import type { Metadata } from "next";
import type { ReactNode } from "react";
import { DM_Sans, Instrument_Sans } from "next/font/google";

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
    default: "Agent Office — AI agents that work as one organization",
    template: "%s · Agent Office",
  },
  description:
    "A collaborative AI workspace where autonomous agents research, plan, build, review, and test together. Bring your own model keys. Free AI mode available.",
  openGraph: {
    title: "Agent Office",
    description: "An operating system for autonomous AI teams.",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Agent Office",
    description: "AI agents that work as one organization.",
  },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${instrument.variable} ${dmSans.variable}`}>
      <body>{children}</body>
    </html>
  );
}
