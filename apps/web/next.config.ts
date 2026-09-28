import type { NextConfig } from "next";

const apiOrigin = process.env.API_ORIGIN || "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // /api/* 反向代理到 FastAPI，前端代码统一 fetch("/api/...")
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${apiOrigin}/api/:path*`,
      },
    ];
  },
  images: {
    // 图片统一走后端代理 /api/img（解决热链），这里允许直接引用代理路径
    remotePatterns: [{ protocol: "http", hostname: "127.0.0.1" }],
  },
};

export default nextConfig;
