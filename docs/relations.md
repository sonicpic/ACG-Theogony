# 关系模型

图谱中的边分为"角色 ↔ 神话体系"与"角色 ↔ 角色"两类。所有关系类型定义于
`theogony/core/enums.py`（`RELATION_META`，唯一权威源），前端展示元数据在
`apps/web/src/lib/constants.ts` 与之保持一致。

## 神话关系（角色 ↔ 神话体系）

| 类型 | 含义 | 方向 |
|---|---|---|
| `BELONGS_TO` | 归属某一神话体系 | 有向 |
| `PROTOTYPE_IS` | 同一原型 | 无向 |
| `GENDER_SWAP` | 性转版本 | 无向 |
| `DERIVED_FROM` | 设定衍生 | 有向 |
| `COMPOSITE_OF` | 多原型复合 | 有向 |

## 家族关系（角色 ↔ 角色）

| 类型 | 含义 | 方向 |
|---|---|---|
| `PARENT_OF` | 父母 | 有向 |
| `SIBLING_OF` | 兄弟姐妹 | 无向 |
| `SPOUSE_OF` | 配偶 | 无向 |
| `LOVER_OF` | 恋人 | 无向 |

## 社会关系（角色 ↔ 角色）

| 类型 | 含义 | 方向 |
|---|---|---|
| `MASTER_OF` | 主人 | 有向 |
| `ALLY_OF` | 盟友 | 无向 |
| `ENEMY_OF` | 敌对 | 无向 |
| `FOUGHT_WITH` | 交手 | 无向 |
| `MENTOR_OF` | 师傅 | 有向 |

## 存储与展示规则

- **方向归一化**：逆关系（`CHILD_OF`/`SERVANT_OF`/`STUDENT_OF`）入库时翻转为
  正向关系存储（见 `theogony/core/seeding.py` 的 `normalize_relationship`）。
- **审核门控**：LLM 挖掘与众包提交的关系一律 `status=pending`，经 `/review` 人工批准后
  才进入默认图谱视图（ADR-0003）。
- **前端呈现**：边颜色取自关系类型配色；悬停约 0.8 秒或点击边可查看
  关系类型与两端角色。

## 新增关系类型的步骤

1. 在 `theogony/core/enums.py` 的 `RELATION_META` 中添加定义（label/category/color/directed）；
2. 运行 `npm run gen` 同步 OpenAPI 与 TS 类型；
3. 在 `apps/web/src/lib/constants.ts` 的 `RELATION_META` 中添加对应的展示元数据；
4. 两端配色保持一致，提交 PR（CI 会校验 schema 漂移）。
