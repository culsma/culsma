# Content Validation Diagrams

## 流程图

```mermaid
flowchart TB
    subgraph Current["当前分支 codex/content-enum-resolution · 第一阶段、2A–2C 已实现"]
        Source["旧裸 token / 字符串<br/>ContentKind.FORMULATION / ContentType.MEDIUM"] --> Frontend["Parser / Compile"]
        Frontend --> Resolver["2A ContentArgumentScope / Resolver<br/>成员、别名、默认值、命名空间遮蔽"]
        Resolver --> Validate["Semantic / Typecheck<br/>成员、枚举族、配对与 cells 约束"]
        Validate --> Flow["本次 2C：控制流中的值失效处理<br/>DeferredContentEnum 保留枚举族<br/>分支内类型检查；运行时别名取值快照"]
        Flow --> Serialize["本次 2C：PlanExpressionSerializer<br/>ContentEnum：enum + member<br/>参数绑定后仍保留枚举身份"]
        Serialize --> Bound["本次 2C：validate_bound_content_plan<br/>静态最终参数复核，含循环体"]
        Bound -->|非法| PlanReject["PLAN_CONTENT_CLASSIFICATION_INVALID<br/>PLAN_CONTAINER_KIND_INVALID<br/>不产生可执行计划"]
        Bound -->|合法或动态待定| Execute["本次 2C：RuntimeValueResolver<br/>枚举求值、赋值、动态引用解析"]
        Execute --> Boundary["本次 2C：content_boundary.py<br/>最终 kind / type 与容器类型复核"]
        Boundary -->|旧文本| Legacy["compat/content_taxonomy.py<br/>旧别名 / fallback / 原分类元数据<br/>历史通用 container token 独立保留"]
        Boundary -->|显式枚举| Strict["准确枚举族与配对<br/>不允许 compat fallback 修正"]
        Legacy --> Classification["2B ContentClassification<br/>真实且不可变的枚举成员<br/>仅合法分类可创建"]
        Strict --> Classification
        Boundary -->|非法| RuntimeReject["MAT_CONTENT_CLASSIFICATION_INVALID<br/>MAT_CONTAINER_KIND_INVALID / MAT_INVALID_CAPACITY<br/>在物料写入前拒绝"]
        Classification --> Store["Runtime registry<br/>kind / type 显式转回既有字符串<br/>保留 attrs 与原始分类元数据"]
        Store --> Science["本次 2C：科学模型分类<br/>ComponentSnapshot.classification<br/>ClassificationRule 使用共享枚举"]
        Note["本次解除 2A 临时执行拦截<br/>PLAN_CONTENT_ENUM_EXECUTION_UNSUPPORTED 已移除<br/>直接成员、别名、参数、分支、循环、cells 与 JSON 往返已测试"]
    end
    Science -.-> Next["下一步 2D · 待实现<br/>reference / 诊断 registry / 实现的机械对照<br/>扩大计算、序列化与回放一致性验收<br/>将 conformance 试点接入 CI"]
    Next -.-> Major["后续大版本<br/>旧源码准入统一退役<br/>历史数据转换独立决定退役时间"]
    Legend["图例<br/>绿色：已实现，本次 2C 在节点中标注<br/>橙色虚线：下一步 2D<br/>灰色：错误出口 / 更晚事项"]
    classDef current fill:#dcfce7,stroke:#15803d,color:#14532d,stroke-width:2px;
    classDef next fill:#ffedd5,stroke:#c2410c,color:#7c2d12,stroke-dasharray:5 5;
    classDef limit fill:#f3f4f6,stroke:#6b7280,color:#374151;
    class Source,Frontend,Resolver,Validate,Flow,Serialize,Bound,Execute,Boundary,Legacy,Strict,Classification,Store,Science,Note current;
    class Next next;
    class PlanReject,RuntimeReject,Major limit;
```

## 时序图

```mermaid
sequenceDiagram
    actor Author as 协议作者
    participant Check as Validate / Typecheck
    participant Plan as Plan / 参数绑定
    participant Values as RuntimeValueResolver
    participant Boundary as content_boundary.py
    participant Legacy as compat 模块
    participant Shared as common/content_contracts.py
    participant Material as 物料状态
    participant Science as 科学模型分类

    rect rgb(220, 252, 231)
        Author->>Check: 直接枚举、别名、参数或旧文本
        Check->>Shared: 2A–2B：成员 / 枚举族 / 静态配对校验
        Shared-->>Check: ContentClassification / 诊断
        Note over Check, Plan: 本次 2C：分支/循环修改值后保留类型，延迟最终值判断
        Check->>Plan: 校验通过的 IR
        Plan->>Plan: 参数绑定；枚举序列化为 enum + member
        Plan->>Boundary: validate_bound_content_plan：复核静态最终值
        Boundary->>Shared: resolve_bound_content_classification / container kind
        Shared-->>Boundary: 有效分类 / 失败
        alt 静态绑定非法
            Boundary-->>Author: PLAN_CONTENT_CLASSIFICATION_INVALID / PLAN_CONTAINER_KIND_INVALID
        else 静态合法或需运行时求值
            Plan->>Values: 执行计划；临时枚举拦截已解除
            Values->>Values: 解码真实枚举、保存赋值快照、求最终参数
            Values->>Boundary: 物料操作前再次验证最终输入
            alt 仅旧文本
                Boundary->>Legacy: normalize_content_classification
                Legacy->>Shared: 合法转换结果提升为 ContentClassification
                Shared-->>Legacy: 分类对象 / None
                Legacy-->>Boundary: 分类及历史元数据
            else 显式枚举
                Boundary->>Shared: 严格枚举族与配对验证，无 fallback
                Shared-->>Boundary: 分类对象 / 失败
            end
            alt 最终值非法
                Boundary-->>Author: MAT_CONTENT_CLASSIFICATION_INVALID / 容器诊断
                Note over Boundary, Material: 不修改 content registry 或无效容器分类
            else 最终值合法
                Boundary->>Material: 成员 value 写入原有字符串字段
                Material->>Science: ComponentSnapshot
                Science->>Shared: classification 提升为枚举分类
                Shared-->>Science: 有效分类 / 未知历史值
                Science->>Science: 枚举规则匹配，未知历史值保留 unknown 行为
            end
        end
    end
    rect rgb(255, 237, 213)
        Note over Check, Science: 下一步 2D：规范表、诊断 registry 与实现对照<br/>扩大计算/运行记录/回放验收，接入 CI<br/>attrs.role 仍开放；code / name 仍为字符串
    end
```

## 类图

```mermaid
classDiagram
    class SharedContentContracts["common/content_contracts.py"]
    class SharedContentContracts {
        +parse_content_classification(kind, type)
        +serialize_content_enum(value)
        +parse_serialized_content_enum(payload)
        +STANDARD_CONTENT_TYPES_BY_KIND_ENUM : readonly
    }
    class ContentKind {
        <<enumeration>>
    }
    class ContentType {
        <<enumeration>>
    }
    class ContainerKind {
        <<enumeration>>
    }
    class ContentClassification {
        +kind : ContentKind
        +type : ContentType
        +validate()
        +to_dict()
    }
    SharedContentContracts ..> ContentKind
    SharedContentContracts ..> ContentType
    SharedContentContracts ..> ContainerKind
    SharedContentContracts ..> ContentClassification : 严格创建
    ContentClassification --> ContentKind
    ContentClassification --> ContentType
    class ContentArgumentResolver
    class DeferredContentEnum {
        +enum_type
    }
    ContentArgumentResolver ..> DeferredContentEnum : 本次：保留控制流后的枚举族
    class PlanExpressionSerializer
    PlanExpressionSerializer ..> SharedContentContracts : 本次：枚举身份序列化
    class BoundContentPlanValidator["plan/content_enums.py"]
    class BoundContentPlanValidator {
        +validate_bound_content_plan(plan)
        +validate_bound_content_step(step)
    }
    class ContentBoundary["pipeline/content_boundary.py"]
    class ContentBoundary {
        +read_bound_content_token(value, expected_enum)
        +resolve_bound_content_classification(kind, type)
        +resolve_bound_container_kind(value)
        +resolve_runtime_container_kind(value)
    }
    class BoundContentClassification {
        +classification : ContentClassification
        +normalization : NormalizedContentClassification or None
    }
    class NormalizedContentClassification {
        +kind : str
        +type : str
        +attrs
        +original_kind
        +original_type
        +classification : ContentClassification or None
    }
    class LegacyContentTaxonomy["compat/content_taxonomy.py"]
    BoundContentPlanValidator ..> ContentBoundary : 本次：绑定后复核
    ContentBoundary ..> SharedContentContracts
    ContentBoundary ..> LegacyContentTaxonomy : 仅旧输入
    ContentBoundary ..> BoundContentClassification : 返回
    BoundContentClassification --> ContentClassification
    BoundContentClassification --> NormalizedContentClassification
    LegacyContentTaxonomy ..> NormalizedContentClassification
    class RuntimeValueResolver
    RuntimeValueResolver ..> SharedContentContracts : 本次：求值与序列化
    class RuntimeContent["runtime/material/container_content.py"]
    RuntimeContent ..> ContentBoundary : 本次：物料写入前复核
    class ComponentSnapshot {
        +canonical_kind : str
        +canonical_type : str
        +classification : ContentClassification or None
    }
    class ClassificationRule {
        +canonical_kind : ContentKind or None
        +canonical_types : ContentType set or None
        +matches_classification(classification)
    }
    ComponentSnapshot ..> SharedContentContracts : 本次：消费者边界提升
    ClassificationRule ..> ContentClassification : 本次：枚举身份匹配
    class EnumConformanceTests {
        <<planned_2D>>
        +reference_and_diagnostic_registry()
        +legacy_compute_and_replay()
        +CI_contract_check()
    }
    EnumConformanceTests ..> SharedContentContracts
    EnumConformanceTests ..> RuntimeContent
    EnumConformanceTests ..> ClassificationRule
    note for ContentBoundary "本次 2C：计划与运行时共用公开边界函数<br/>test_content_enum_execution.py 验收<br/>非法最终值在物料写入前拒绝"
    note for BoundContentPlanValidator "原 2A 临时 guard 已移除<br/>本次改为最终绑定值校验，不再禁止合法枚举执行"
    note for NormalizedContentClassification "历史字符串、attrs 与原分类元数据继续保留<br/>旧源码准入退役不影响独立历史适配"
    note for EnumConformanceTests "图例：绿色已实现；橙色下一步 2D<br/>本次包含 JSON 往返与旧协议回归，广泛规范对照仍待完成"
    style SharedContentContracts fill:#dcfce7,stroke:#15803d,color:#14532d
    style ContentClassification fill:#dcfce7,stroke:#15803d,color:#14532d
    style DeferredContentEnum fill:#dcfce7,stroke:#15803d,color:#14532d
    style PlanExpressionSerializer fill:#dcfce7,stroke:#15803d,color:#14532d
    style BoundContentPlanValidator fill:#dcfce7,stroke:#15803d,color:#14532d
    style ContentBoundary fill:#dcfce7,stroke:#15803d,color:#14532d
    style BoundContentClassification fill:#dcfce7,stroke:#15803d,color:#14532d
    style RuntimeValueResolver fill:#dcfce7,stroke:#15803d,color:#14532d
    style RuntimeContent fill:#dcfce7,stroke:#15803d,color:#14532d
    style ComponentSnapshot fill:#dcfce7,stroke:#15803d,color:#14532d
    style ClassificationRule fill:#dcfce7,stroke:#15803d,color:#14532d
    style EnumConformanceTests fill:#ffedd5,stroke:#c2410c,color:#7c2d12,stroke-dasharray:5 5
```
