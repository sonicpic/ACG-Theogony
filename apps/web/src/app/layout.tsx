import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "@/components/providers";
import { Nav } from "@/components/nav";

export const metadata: Metadata = {
  title: {
    default: "神谱图谱 Theogony",
    template: "%s · 神谱图谱",
  },
  description:
    "ACG 角色 × 神话原型关系知识图谱：路径探索、家谱树、AI 问答、每日猜角色",
  openGraph: {
    title: "神谱图谱 Theogony",
    description: "ACG 角色 × 神话原型关系知识图谱",
    type: "website",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body className="min-h-screen antialiased">
        <Providers>
          <Nav />
          {children}
        </Providers>
      </body>
    </html>
  );
}
