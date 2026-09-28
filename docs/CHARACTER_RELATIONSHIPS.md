# 角色关系可视化指南

## 概述

Theogony-Graph 支持可视化角色之间的各种关系，包括家族关系（父子、兄弟姐妹）、社会关系（盟友、敌对、战斗）等。

## 关系类型

### 神话关系（角色 ↔ 神话体系）
- `BELONGS_TO` - 归属某一神话体系
- `PROTOTYPE_IS` - 原型关系（同一人物）
- `GENDER_SWAP` - 性转版本
- `DERIVED_FROM` - 设定衍生
- `COMPOSITE_OF` - 多原型复合

### 家族关系（角色 ↔ 角色）
- `PARENT_OF` - 父母关系（显示方向箭头）
- `CHILD_OF` - 子女关系（显示方向箭头）
- `SIBLING_OF` - 兄弟姐妹（双向）
- `SPOUSE_OF` - 配偶关系（双向）
- `LOVER_OF` - 恋人关系（双向）

### 社会关系（角色 ↔ 角色）
- `MASTER_OF` - 主人（显示方向箭头）
- `SERVANT_OF` - 从者（显示方向箭头）
- `ALLY_OF` - 盟友/同伴（双向）
- `ENEMY_OF` - 敌对关系（双向）
- `FOUGHT_WITH` - 战斗过（双向）
- `MENTOR_OF` - 师傅（显示方向箭头）
- `STUDENT_OF` - 学生（显示方向箭头）

## 添加新关系

编辑 `backend/data/character_relationships.json`：

```json
{
  "relationships": [
    {
      "source_name": "阿尔托莉雅·潘德拉贡",
      "target_name": "莫德雷德",
      "relationship": "PARENT_OF",
      "bidirectional": false
    }
  ]
}
```

### 字段说明

- `source_name`: 源角色名称（需与 `raw_characters.json` 中的 `name` 或 `prototype` 字段匹配）
- `target_name`: 目标角色名称
- `relationship`: 关系类型（必须是 `RelationshipType` 枚举中的有效值）
- `bidirectional`: 是否双向关系
  - `true`: 会创建两条连线（A→B 和 B→A）
  - `false`: 只创建单向连线（A→B）

### 注意事项

1. **名称匹配规则**：
   - 优先匹配角色的 `name` 字段
   - 如果未找到，再匹配 `prototype` 字段
   - 大小写敏感，需精确匹配
   - 如果找不到对应角色，该关系会被跳过

2. **双向关系建议**：
   - 家族关系：`SIBLING_OF`, `SPOUSE_OF`, `LOVER_OF` 使用 `bidirectional: true`
   - 社会关系：`ALLY_OF`, `ENEMY_OF`, `FOUGHT_WITH` 使用 `bidirectional: true`
   - 层级关系：`PARENT_OF`, `MASTER_OF`, `MENTOR_OF` 使用 `bidirectional: false`

3. **互补关系**：
   - 如果添加了 `A PARENT_OF B`，可以额外添加 `B CHILD_OF A`
   - 如果添加了 `A MASTER_OF B`，可以额外添加 `B SERVANT_OF A`

## 可视化效果

- **颜色编码**：不同关系类型使用不同颜色的连线
- **方向箭头**：层级关系（父子、师徒等）显示移动的粒子箭头
- **筛选功能**：前端支持按类别筛选关系类型
- **交互高亮**：点击节点会高亮所有相关连线

## 重新构建图谱

添加或修改关系后，需要重新构建图谱：

```bash
# 在项目根目录执行
python -m backend.build_graph
```

构建脚本会输出：
- 成功添加的关系数量
- 跳过的关系数量（角色未找到或关系类型无效）
- 关系类型分布统计

## 示例关系

项目预置了以下示例关系：

### 家族关系
- 阿尔托莉雅·潘德拉贡 → 莫德雷德（父母）
- 迦尔纳 ↔ 阿周那（兄弟）
- 项羽 ↔ 虞美人（配偶）

### 战斗关系
- 阿喀琉斯 ↔ 赫克托尔（战斗、敌对）
- 源赖光 ↔ 酒吞童子（战斗、敌对）

### 盟友关系
- 吉尔伽美什 ↔ 恩奇都（盟友）

### 师徒关系
- 斯卡哈 → 库·丘林（师傅）

## 扩展新关系类型

如需添加新的关系类型：

1. 在 `backend/schema.py` 的 `RelationshipType` 枚举中添加
2. 在 `frontend/src/types.ts` 的 `RelationshipType` 类型中添加
3. 在 `frontend/src/components/TheogonyGraph.tsx` 的 `relationshipConfig` 中配置颜色和显示名称
4. 如果是方向性关系，在 `linkDirectionalParticles` 函数中添加

## 故障排除

### 关系未显示
1. 检查 `source_name` 和 `target_name` 是否与原始数据完全匹配
2. 查看构建输出中的"跳过"数量
3. 确认关系类型拼写正确（区分大小写）

### 箭头未显示
- 检查该关系类型是否在 `linkDirectionalParticles` 的 `directionalRelations` 数组中

### 颜色不正确
- 在 `relationshipConfig` 中配置该关系类型的颜色
