/**
 * Theogony-Graph 统一数据结构定义
 *
 * 与后端 backend/schema.py 保持同步。
 * 任何结构变更必须两边一起改。
 */

// ──────────────────────────────────────────────
// 枚举
// ──────────────────────────────────────────────

/** 节点类型 */
export type NodeType = "Character" | "Myth";

/** 关系类型 */
export type RelationshipType =
  // ── 角色 ↔ 神话体系 ──
  | "PROTOTYPE_IS"   // 角色 → 神话原型（同一人物）
  | "GENDER_SWAP"    // 性转版本
  | "BELONGS_TO"     // 归属某一神话体系
  | "DERIVED_FROM"   // 设定衍生
  | "COMPOSITE_OF"   // 多原型复合
  // ── 角色 ↔ 角色（家族/血缘）──
  | "PARENT_OF"      // 父母关系
  | "CHILD_OF"       // 子女关系
  | "SIBLING_OF"     // 兄弟姐妹
  | "SPOUSE_OF"      // 配偶关系
  | "LOVER_OF"       // 恋人关系
  // ── 角色 ↔ 角色（社会关系）──
  | "MASTER_OF"      // 主仆关系（主人）
  | "SERVANT_OF"     // 主仆关系（从者）
  | "ALLY_OF"        // 盟友/同伴
  | "ENEMY_OF"       // 敌对关系
  | "FOUGHT_WITH"    // 战斗过
  | "MENTOR_OF"      // 师徒关系（师傅）
  | "STUDENT_OF";    // 师徒关系（学生）

// ──────────────────────────────────────────────
// 数据类型
// ──────────────────────────────────────────────

/** 图谱节点 */
export interface GraphNode {
  /** 唯一标识：角色用 "char_<id>"，神话用 "myth_<slug>" */
  id: string;
  /** 显示名称 */
  name: string;
  /** 节点类型 */
  type: NodeType;
  /** 出处，如 "Fate/Grand Order" */
  source?: string;
  /** 简短描述 */
  description?: string;
  /** 可选头像 URL */
  image_url?: string;
  /** 额外属性（职阶、地域等） */
  metadata?: Record<string, unknown>;

  // ── react-force-graph 运行时注入的属性 ──
  x?: number;
  y?: number;
  vx?: number;
  vy?: number;
  fx?: number;
  fy?: number;
}

/** 图谱连线 */
export interface GraphLink {
  /** 起始节点 ID */
  source: string | GraphNode;
  /** 目标节点 ID */
  target: string | GraphNode;
  /** 关系类型 */
  relationship: RelationshipType;
  /** 显示标签 */
  label?: string;
}

/** 完整图谱数据（匹配 react-force-graph 的输入格式） */
export interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}
