import type { NextConfig } from "next";

// Backend URLs are configurable via env vars so this app can point at
// different environments (local dev, staging, etc.) without code changes.
const CHAT_BACKEND_URL = process.env.CHAT_BACKEND_URL || "http://127.0.0.1:8000";
const DOCBOT_BACKEND_URL = process.env.DOCBOT_BACKEND_URL || "http://127.0.0.1:5000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      // /api/chat/message -> {CHAT_BACKEND_URL}/api/message
      { source: "/api/chat/:path*", destination: `${CHAT_BACKEND_URL}/api/:path*` },
      // /api/docbot/index -> {DOCBOT_BACKEND_URL}/api/index
      { source: "/api/docbot/:path*", destination: `${DOCBOT_BACKEND_URL}/api/:path*` },
    ];
  },
};

export default nextConfig;
