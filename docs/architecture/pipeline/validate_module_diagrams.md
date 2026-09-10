# Content Validation Diagrams

## 流程图

```mermaid
flowchart TB
    subgraph Current["当前分支 codex/content-enum-resolution · 第一阶段、2A 与 2B 已实现"]
        Source["旧裸 token / 字符串<br/>ContentKind.FORMULATION / ContentType.MEDIUM"] --> Compile["Parser / Compile → IR"]
        Compile --> Scope["ContentArgumentScope<br/>字面值、表达式绑定、已声明名称"]
        Scope --> Resolver["ContentArgumentResolver · 2A 已实现<br/>成员、别名、参数默认值、赋值快照<br/>同名遮蔽、循环检测"]
        Resolver --> Shared["common/content_contracts.py · 本次 2B 迁入配对契约<br/>只读配对表与统一分类创建入口<br/>原 content_vocab 路径重导出"]
        Resolver --> Legacy["compat/content_syntax.py<br/>旧文本准入规则集中保留"]
        Shared --> Result["ContentEnumResolution<br/>实际值、预期枚举族、来源、状态"]
        Legacy --> Result
        Result --> Check["Binding / Validate / Typecheck · 本次接入强类型分类<br/>非法成员与循环：semantic<br/>错误枚举族与非文本：typecheck<br/>词表、配对、surface / cells 约束继续检查"]
        Check --> Pair{"旧分类需要兼容转换？"}
        Pair -->|仅旧输入| Normalize["compat/content_taxonomy.py<br/>别名 / fallback / 原始元数据与警告"]
        Pair -->|包含显式枚举| Exact["非法配对直接拒绝<br/>compat 也不能修正枚举输入"]
        Normalize --> Promotion["本次 2B：normalized.classification<br/>合法结果提升为强类型对象<br/>未知历史值保留原数据，返回 None"]
        Promotion -->|合法| Classification
        Exact -->|校验通过| Classification
        Classification --> Plan["Plan；IR 尚未携带分类对象"]
        Plan --> Guard{"是否残留未降级的内容枚举成员？"}
        Guard -->|是| Stop["2A 执行保护 · 继续保留<br/>PLAN_CONTENT_ENUM_EXECUTION_UNSUPPORTED<br/>不产生可执行计划，防止写入空分类"]
        Guard -->|否| Runtime["现有 Runtime<br/>旧协议执行、registry 与 JSON 保持兼容"]
        Check --> Deferred["未确定的参数仍 deferred<br/>最终绑定值检查属于 2C"]
    end

    subgraph ClassificationContract["本次 2B · 已实现"]
        Classification["ContentClassification<br/>不可变 ContentKind / ContentType 成员<br/>validate：拒绝错误枚举族和非法配对<br/>to_dict：显式输出字符串"]
        PairContract["parse_content_classification<br/>只接受准确 canonical 值，不做兼容转换<br/>与旧输入及历史转换结果分开"]
        PairContract --> Classification
    end
    Check --> PairContract
    Classification -.-> Boundary["下一步 2C · 待实现<br/>绑定后、物料更新前复核<br/>Plan / Runtime 保留枚举身份<br/>接通后移除 2A 执行保护"]
    Boundary -.-> Conformance["后续 2D · 待实现<br/>reference 与实现一致性<br/>计算、序列化、运行及回放验收"]
    Conformance -.-> Retirement["后续大版本<br/>统一移除旧源码准入模块<br/>历史数据适配独立决定退役时间"]
    Legend["图例<br/>绿色：已实现；本次改动在节点中标注<br/>橙色虚线：下一步 2C<br/>紫色虚线：后续 2D<br/>灰色：当前限制 / 更晚事项"]
    classDef current fill:#dcfce7,stroke:#15803d,color:#14532d,stroke-width:2px;
    classDef next fill:#ffedd5,stroke:#c2410c,color:#7c2d12,stroke-dasharray:5 5;
    classDef later fill:#ede9fe,stroke:#7c3aed,color:#4c1d95,stroke-dasharray:5 5;
    classDef limit fill:#f3f4f6,stroke:#6b7280,color:#374151;
    class Source,Compile,Scope,Resolver,Shared,Legacy,Result,Check,Normalize,Exact,Plan,Runtime current;
    class Classification,PairContract,Promotion current;
    class Boundary next;
    class Conformance later;
    class Stop,Deferred,Retirement limit;
```

## 时序图

```mermaid
sequenceDiagram
    actor Author as 协议作者
    participant Frontend as Parser / Compile
    participant Check as Binding / Validate / Typecheck
    participant Resolver as ContentArgumentResolver
    participant Scope as ContentArgumentScope
    participant Shared as 共享枚举契约
    participant Legacy as compat 模块
    participant Plan as Plan
    participant Runtime as Runtime

    rect rgb(220, 252, 231)
        Note over Author, Plan: 当前 2A–2B 已实现：解析与强类型分类均有测试覆盖
        Author->>Frontend: 直接成员、let 别名、默认值或旧文本
        Frontend->>Check: Canonical IR + analysis
        Check->>Resolver: resolve_argument(expr, expected_enum, scope)
        Resolver->>Scope: 查询当前绑定，局部名称优先
        Scope-->>Resolver: 已知值 / 表达式 / 未确定参数
        alt 真正的枚举成员
            Resolver->>Shared: resolve_content_enum_member(enum_type, member)
            Shared-->>Resolver: 枚举成员 / 非法成员
        else 已完成绑定解析的旧文本
            Resolver->>Legacy: resolve_legacy_content_token(value)
            Legacy-->>Resolver: 旧文本候选值
        else 未确定参数或错误输入
            Resolver->>Resolver: deferred / invalid
        end
        Resolver-->>Check: 值、预期枚举族、来源、状态与错误原因
        Check->>Check: 诊断归属与静态词表、配对、surface / cells 校验
        Check->>Shared: 本次 2B：parse_content_classification(kind, type)
        Shared-->>Check: ContentClassification / None
        opt 仅旧输入需要转换
            Check->>Legacy: normalize_content_classification
            Legacy->>Shared: normalized.classification 复用严格创建入口
            Shared-->>Legacy: 有效分类对象 / None（未知历史数据）
            Legacy-->>Check: 强类型分类、原分类元数据与警告
        end
        Note over Check, Legacy: 含显式枚举的错误配对在 strict / compat 都拒绝
        Check->>Plan: 校验通过的 IR
        alt 残留未降级内容枚举
            Plan-->>Author: PLAN_CONTENT_ENUM_EXECUTION_UNSUPPORTED
            Note over Plan, Runtime: 2A 不执行此计划，避免 kind / type 被写成空值
        else 现有旧输入路径
            Plan->>Runtime: 沿用已有执行语义
        end
    end

    rect rgb(255, 237, 213)
        Note over Check, Runtime: 下一步 2C 待实现：携带分类对象贯通执行
        Check->>Plan: 2C 枚举身份进入计划与绑定
        Plan->>Shared: 2C 最终绑定值复核
        Shared-->>Plan: 有效分类 / 明确诊断
        Plan->>Runtime: 2C 接通后解除执行保护
        Runtime->>Shared: 物料更新前复核
    end
    rect rgb(237, 233, 254)
        Note over Legacy, Runtime: 后续 2D：旧协议计算、JSON、回放和 reference 对照<br/>attrs.role 保持开放，code / name 保持字符串
    end
```

## 类图

```mermaid
classDiagram
    class SharedContentContracts["common/content_contracts.py"]
    class SharedContentContracts {
        +resolve_content_enum_member(enum_type, member)
        +parse_content_classification(kind, type)
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
    SharedContentContracts ..> ContentKind : 定义
    SharedContentContracts ..> ContentType : 定义
    SharedContentContracts ..> ContainerKind : 定义
    class ContentVocabulary["pipeline/content_vocab.py"]
    ContentVocabulary ..> SharedContentContracts : 同一枚举类、配对表与查询函数重导出
    class ContentArgumentScope {
        +literal_bindings
        +expr_bindings
        +defined_names
        +has_binding(name)
    }
    class ContentArgumentResolver {
        +resolve_argument(expr, expected_enum, scope)
        +resolve_enum_member(expr, expected_enum, scope)
        +resolve_binding(name, expected_enum, scope)
        +resolve_enum_value(value, expected_enum)
    }
    class ContentEnumResolution {
        +value : enum or legacy text
        +expected_enum
        +source : enum or legacy or unknown
        +status : resolved or deferred or invalid
        +issue
        +token
    }
    class LegacyContentSyntax["compat/content_syntax.py"]
    class LegacyContentSyntax {
        +resolve_legacy_content_token(value)
        +normalization_diagnostics(...)
    }
    class LegacyContentTaxonomy["compat/content_taxonomy.py"]
    class NormalizedContentClassification {
        +kind : str
        +type : str
        +attrs
        +original_kind
        +original_type
        +classification : ContentClassification or None
    }
    LegacyContentTaxonomy ..> NormalizedContentClassification : 保留兼容结果
    NormalizedContentClassification ..> SharedContentContracts : 本次 2B 合法结果提升
    class ConstructorValidator
    class TypecheckExpressionServices
    class BindingValidator
    ConstructorValidator ..> ContentArgumentResolver
    TypecheckExpressionServices ..> ContentArgumentResolver
    BindingValidator ..> ContentArgumentResolver
    ContentArgumentResolver ..> ContentArgumentScope
    ContentArgumentResolver ..> ContentEnumResolution : 返回
    ContentArgumentResolver ..> SharedContentContracts : 保留枚举身份
    ContentArgumentResolver ..> LegacyContentSyntax : 旧文本准入
    ConstructorValidator ..> SharedContentContracts : 本次 2B 严格创建分类
    TypecheckExpressionServices ..> SharedContentContracts : 本次 2B cells 检查使用枚举身份
    ConstructorValidator ..> LegacyContentSyntax : 兼容诊断
    LegacyContentSyntax ..> LegacyContentTaxonomy : 兼容转换
    class ContentEnumExecutionGuard["plan/content_enums.py"]
    class ContentEnumExecutionGuard {
        +contains_member_expression(value)
        +has_unlowered_content_enum(value)
        +guard_content_enum_execution(plan)
    }
    class Plan
    class RuntimeContent
    Plan ..> ContentEnumExecutionGuard : 2A 拦截未支持的执行
    RuntimeContent ..> LegacyContentTaxonomy : 历史分类转换
    class ContentClassification {
        +kind : ContentKind
        +type : ContentType
        +validate()
        +to_dict()
    }
    SharedContentContracts ..> ContentClassification : 本次 2B：验证配对后创建
    ContentClassification --> ContentKind
    ContentClassification --> ContentType
    class ContentBoundaryValidator {
        <<planned_2C>>
        +validate_bound_inputs(...)
        +validate_before_material_update(...)
    }
    ContentBoundaryValidator ..> ContentClassification
    Plan ..> ContentBoundaryValidator : 2C 待接入
    RuntimeContent ..> ContentBoundaryValidator : 2C 待接入
    class EnumConformanceTests {
        <<planned_2D>>
        +reference_contracts()
        +source_to_run_and_replay()
        +legacy_compute_and_serialization()
    }
    EnumConformanceTests ..> ContentBoundaryValidator
    note for ContentArgumentResolver "2A 已实现 · pipeline/content_inputs.py<br/>成员、别名、默认值、遮蔽、循环与赋值快照<br/>test_content_inputs.py + test_content_enum_resolution.py"
    note for SharedContentContracts "本次 2B：配对表迁入共享层，防止运行中修改<br/>校验、类型检查与兼容提升共用严格创建入口<br/>test_content_classification.py 验收"
    note for ContentEnumExecutionGuard "2A 保护继续保留：阻止空分类写入<br/>PLAN_CONTENT_ENUM_EXECUTION_UNSUPPORTED<br/>2C 执行端接通后移除"
    note for LegacyContentSyntax "旧源码规则集中保留<br/>大版本移除时与历史数据适配分开"
    note for ContentClassification "图例：绿色已实现；橙色下一步 2C<br/>紫色后续 2D；灰色执行限制"
    style ContentArgumentScope fill:#dcfce7,stroke:#15803d,color:#14532d
    style ContentArgumentResolver fill:#dcfce7,stroke:#15803d,color:#14532d
    style ContentEnumResolution fill:#dcfce7,stroke:#15803d,color:#14532d
    style SharedContentContracts fill:#dcfce7,stroke:#15803d,color:#14532d
    style ContentVocabulary fill:#dcfce7,stroke:#15803d,color:#14532d
    style ConstructorValidator fill:#dcfce7,stroke:#15803d,color:#14532d
    style TypecheckExpressionServices fill:#dcfce7,stroke:#15803d,color:#14532d
    style BindingValidator fill:#dcfce7,stroke:#15803d,color:#14532d
    style LegacyContentSyntax fill:#dcfce7,stroke:#15803d,color:#14532d
    style LegacyContentTaxonomy fill:#dcfce7,stroke:#15803d,color:#14532d
    style ContentEnumExecutionGuard fill:#f3f4f6,stroke:#6b7280,color:#374151
    style ContentClassification fill:#dcfce7,stroke:#15803d,color:#14532d
    style NormalizedContentClassification fill:#dcfce7,stroke:#15803d,color:#14532d
    style ContentBoundaryValidator fill:#ffedd5,stroke:#c2410c,color:#7c2d12,stroke-dasharray:5 5
    style EnumConformanceTests fill:#ede9fe,stroke:#7c3aed,color:#4c1d95,stroke-dasharray:5 5
```
