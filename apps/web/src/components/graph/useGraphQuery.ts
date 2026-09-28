"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

/** 全量图谱数据（一次拉取，客户端交互零延迟）。 */
export function useGraphQuery() {
  return useQuery({
    queryKey: ["graph", "full"],
    queryFn: () => api.graph({ includeMythNodes: true }),
  });
}
