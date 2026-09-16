import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Produces a minimal self-contained server bundle for the production image.
  output: "standalone",
  reactStrictMode: true,
};

export default nextConfig;
