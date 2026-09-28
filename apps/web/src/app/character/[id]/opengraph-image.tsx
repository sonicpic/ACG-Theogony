/** OG 分享卡（Next.js ImageResponse）。 */

import { ImageResponse } from "next/og";

export const size = { width: 1200, height: 630 };
export const contentType = "image/png";
export const alt = "神谱图谱角色卡";

const API = process.env.API_ORIGIN || "http://127.0.0.1:8000";

export default async function OgImage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let name = "未知角色";
  let mythology = "";
  let degree = 0;
  let className = "";
  try {
    const res = await fetch(`${API}/api/characters/${id}`, { next: { revalidate: 3600 } });
    if (res.ok) {
      const c = (await res.json()) as { name: string; mythology?: string; degree: number; className: string };
      name = c.name;
      mythology = c.mythology || "";
      degree = c.degree;
      className = c.className;
    }
  } catch {
    /* 保持默认 */
  }

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          padding: 80,
          background: "linear-gradient(135deg, #0c0d14 0%, #1a1b2e 60%, #2b1b3d 100%)",
          color: "#e4e4e7",
          fontFamily: "sans-serif",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12, fontSize: 26, color: "#71717a" }}>
          <div
            style={{
              width: 18,
              height: 18,
              borderRadius: 9,
              background: "linear-gradient(135deg, #38bdf8, #8b5cf6)",
            }}
          />
          神谱图谱 Theogony · ACG × 神话
        </div>
        <div style={{ fontSize: 84, fontWeight: 700, marginTop: 36 }}>{name}</div>
        <div style={{ display: "flex", gap: 20, marginTop: 30, fontSize: 32, color: "#a1a1aa" }}>
          {className && <div>职阶 {className}</div>}
          {mythology && <div>{mythology}</div>}
          <div>关系 {degree}</div>
        </div>
        <div style={{ marginTop: "auto", fontSize: 24, color: "#52525b" }}>
          localhost:3000/character/{id}
        </div>
      </div>
    ),
    size
  );
}
