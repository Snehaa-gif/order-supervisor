import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Hide the floating dev-mode badge so it doesn't appear in demos/recordings.
  devIndicators: false,
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
