"use client";

import { BRAND_LOGO_PNG, BRAND_LOGO_SRC, BRAND_NAME } from "@/lib/brand";

export function BrandLogo({
  size = 34,
  className = "",
  title = BRAND_NAME,
  /** Prefer PNG for larger UI marks; SVG for tiny/favicon-like slots. */
  variant = "png",
}: {
  size?: number;
  className?: string;
  title?: string;
  variant?: "png" | "svg";
}) {
  const src = variant === "svg" ? BRAND_LOGO_SRC : BRAND_LOGO_PNG;
  return (
    // eslint-disable-next-line @next/next/no-img-element -- local brand asset
    <img
      src={src}
      alt=""
      width={size}
      height={size}
      className={`brand-logo ${className}`.trim()}
      title={title}
      decoding="async"
    />
  );
}

export function BrandWordmark({
  href = "/",
  size = 28,
  showWord = true,
  className = "",
}: {
  href?: string;
  size?: number;
  showWord?: boolean;
  className?: string;
}) {
  return (
    <a href={href} className={`brand-wordmark ${className}`.trim()} aria-label={BRAND_NAME}>
      <BrandLogo size={size} />
      {showWord ? <span className="brand-wordmark-text">{BRAND_NAME}</span> : null}
    </a>
  );
}
