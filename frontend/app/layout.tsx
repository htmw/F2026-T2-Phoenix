import type { Metadata } from "next";
import type { ReactNode } from "react";
import { DM_Sans, Instrument_Sans } from "next/font/google";

import { ThemeProvider } from "@/components/ThemeProvider";
import { BRAND_MARK_SRC, BRAND_NAME, BRAND_TAGLINE, BRAND_WORDMARK_SRC } from "@/lib/brand";
import { THEME_BOOT_SCRIPT } from "@/lib/theme";

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
    default: `${BRAND_NAME} — ${BRAND_TAGLINE}`,
    template: `%s · ${BRAND_NAME}`,
  },
  description: `Describe any goal — market research, a product plan, analysis, or code — and ${BRAND_NAME} assembles a team of AI specialists to deliver it. Bring your own model keys. Free AI mode available.`,
  icons: {
    icon: [{ url: BRAND_MARK_SRC, type: "image/png" }],
    apple: BRAND_MARK_SRC,
  },
  openGraph: {
    title: BRAND_NAME,
    description: BRAND_TAGLINE,
    type: "website",
    images: [{ url: BRAND_WORDMARK_SRC }],
  },
  twitter: {
    card: "summary_large_image",
    title: BRAND_NAME,
    description: BRAND_TAGLINE,
    images: [BRAND_WORDMARK_SRC],
  },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${instrument.variable} ${dmSans.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT_SCRIPT }} />
      </head>
      <body>
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
