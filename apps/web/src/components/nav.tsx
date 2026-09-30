"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import clsx from "clsx";
import { Network, BadgeCheck, BarChart3, Dna, Gamepad2, Radar } from "lucide-react";

const items = [
  { href: "/", label: "图谱", icon: Network },
  { href: "/prototypes", label: "原型雷达", icon: Radar },
  { href: "/dna", label: "神话DNA", icon: Dna },
  { href: "/review", label: "审核", icon: BadgeCheck },
  { href: "/stats", label: "看板", icon: BarChart3 },
  { href: "/game", label: "猜角色", icon: Gamepad2 },
];

export function Nav() {
  const pathname = usePathname();
  if (pathname?.startsWith("/embed/")) return null;
  return (
    <header className="sticky top-0 z-40 border-b border-zinc-800 bg-zinc-950/80 backdrop-blur">
      <div className="mx-auto flex h-12 max-w-[1600px] items-center gap-6 px-4">
        <Link href="/" className="flex items-center gap-2 font-semibold tracking-wide">
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-gradient-to-br from-sky-400 to-violet-500" />
          神谱图谱
          <span className="hidden text-xs font-normal text-zinc-500 sm:inline">Theogony v2</span>
        </Link>
        <nav className="flex items-center gap-1 text-sm">
          {items.map(({ href, label, icon: Icon }) => {
            const active = href === "/" ? pathname === "/" : pathname?.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={clsx(
                  "flex items-center gap-1.5 rounded-md px-3 py-1.5 transition-colors",
                  active ? "bg-zinc-800 text-white" : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"
                )}
              >
                <Icon size={14} />
                {label}
              </Link>
            );
          })}
        </nav>
        <div className="ml-auto hidden text-xs text-zinc-600 md:block">
          ACG × 神话 · 知识图谱
        </div>
      </div>
    </header>
  );
}
