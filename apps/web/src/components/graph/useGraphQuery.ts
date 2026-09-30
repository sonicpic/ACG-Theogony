"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

/** 全量图谱数据（一次拉取，客户端交互零延迟）。
 *  staleTime Infinity + 禁止焦点重取：数据是会话内静态的，
 *  若后台 refetch 产生新对象引用，SigmaGraph 会整体重挂载 → 相机重置/布局重跑（视图跳动）。 */
export function useGraphQuery() {
  return useQuery({
    queryKey: ["graph", "full"],
    queryFn: () => api.graph({ includeMythNodes: true }),
    staleTime: Infinity,
    gcTime: Infinity,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });
}
