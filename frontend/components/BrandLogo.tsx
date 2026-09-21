"use client";

import {
  BRAND_MARK_SRC,
  BRAND_NAME,
  BRAND_WORDMARK_SRC,
} from "@/lib/brand";

export function BrandLogo({
  size = 34,
  className = "",
  title = BRAND_NAME,
  /** Square mark for compact slots; wordmark image for rare fixed assets. */
  variant = "mark",
}: {
  size?: number;
  className?: string;
  title?: string;
  variant?: "mark" | "wordmark";
}) {
  if (variant === "wordmark") {
    const height = size;
    const width = Math.round(size * 4);
    return (
      // eslint-disable-next-line @next/next/no-img-element -- local brand asset
      <img
        src={BRAND_WORDMARK_SRC}
        alt={title}
        height={height}
        width={width}
        className={`brand-logo brand-logo-wordmark ${className}`.trim()}
        title={title}
        decoding="async"
      />
    );
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element -- local brand asset
    <img
      src={BRAND_MARK_SRC}
      alt=""
      width={size}
      height={size}
      className={`brand-logo ${className}`.trim()}
      title={title}
      decoding="async"
    />
  );
}

/** Theme-safe header mark: icon + text colored with CSS (readable in light and dark). */
export function BrandWordmark({
  href = "/",
  size = 36,
  className = "",
}: {
  href?: string;
  size?: number;
  className?: string;
}) {
  return (
    <a href={href} className={`brand-wordmark ${className}`.trim()} aria-label={BRAND_NAME}>
      <BrandLogo size={size} variant="mark" />
      <span className="brand-wordmark-text">{BRAND_NAME}</span>
    </a>
  );
}
