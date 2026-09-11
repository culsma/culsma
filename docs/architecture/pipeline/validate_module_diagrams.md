# Content Validation Diagrams

## 流程图

```mermaid
flowchart TB
    subgraph Pipeline["内容校验与执行"]
        Source["源码：裸 token、字符串、显式枚举"] --> Frontend["Parser / Frontend / Compile<br/>展开时保留原始 Span 来源"]
        Frontend --> Names["OperationContractValidator<br/>通用调用与嵌套 content 共用参数名检查<br/>允许参数来自 BUILTIN_OPERATION_SPECS"]
        Names --> Resolver["ContentArgumentScope / Resolver<br/>成员、别名、默认值、遮蔽与赋值快照"]
        Resolver --> Checks["Semantic / Typecheck<br/>枚举族、成员、kind/type 配对、cells<br/>控制流改变值后保留类型并延迟最终值判断"]
        Checks --> Diagnostics["deduplicate_diagnostics<br/>共享 Span 对象确认同一源码来源<br/>不同来源、消息或严重度分别保留"]
        Diagnostics --> Gate{"校验通过？"}
        Gate -->|否| Reject["阻止执行<br/>未知参数 / 重复参数 / 分类错误"]
        Gate -->|是| Plan["PlanExpressionSerializer<br/>ContentEnum 保存 enum + member<br/>绑定后的静态值由 validate_bound_content_plan 复核"]
        Plan -->|非法| Reject
        Plan -->|合法或动态待定| Values["RuntimeValueResolver<br/>枚举解码、动态取值与别名快照"]
        Values --> Boundary["content_boundary.py<br/>物料写入前检查最终分类与容器 kind"]
        Boundary -->|非法| RuntimeReject["MAT 诊断<br/>拒绝受影响的物料写入"]
        Boundary -->|显式枚举| Shared["common/content_contracts.py<br/>真实枚举、只读配对表<br/>不可变 ContentClassification"]
        Boundary -->|旧文本| History["compat/content_taxonomy.py<br/>别名、fallback、原分类及推断属性"]
        History --> Shared
        Shared --> Material["物料记录<br/>分类字段写入 canonical 字符串<br/>保留显式 attrs 和兼容元数据"]
        Material --> Science["科学模型<br/>ComponentSnapshot 提升分类<br/>ClassificationRule 使用共享枚举"]
        Resolver --> LegacySource["compat/content_syntax.py<br/>旧源码准入及兼容诊断"]
    end
    subgraph Conformance["实现仓库维护的符合性证据"]
        Reference["独立 reference<br/>语言行为、诊断契约、Req ID 与验收标准"] --> Extract["conformance/content_contract.py<br/>提取拥有契约的章节"]
        Extract --> Snapshot["content_reference.json<br/>派生契约、原章节、路径与 SHA-256"]
        Hooks["test_hooks.json<br/>实现维护的 Req ID → 测试入口"] --> Checker["检查规范漂移、实现差异与失效测试映射"]
        Snapshot --> Checker
        Shared -.-> Checker
        History -.-> Checker
        Checker --> Evidence["源码入口、参数错误、推荐 role、旧值转换<br/>数量计算、序列化与事件回放"]
        CodeCI["实现 PR CI：固定快照<br/>实现仓库手动工作流：指定 reference revision"] --> Checker
    end
    note["源码兼容与历史记录转换分别维护<br/>reference 不读取实现代码；runtime 不读取 reference<br/>当前机械对照覆盖内容契约，不代表全部规范表已覆盖"]
    classDef stage fill:#dcfce7,stroke:#15803d,color:#14532d;
    classDef evidence fill:#dbeafe,stroke:#2563eb,color:#1e3a8a;
    classDef stop fill:#f3f4f6,stroke:#6b7280,color:#374151;
    class Source,Frontend,Names,Resolver,Checks,Diagnostics,Plan,Values,Boundary,Shared,History,Material,Science,LegacySource stage;
    class Reference,Extract,Snapshot,Hooks,Checker,Evidence,CodeCI evidence;
    class Reject,RuntimeReject,note stop;
```

## 时序图

```mermaid
sequenceDiagram
    actor Author as 协议作者
    participant Frontend as Frontend / Compile
    participant Validate as Semantic / Typecheck
    participant Shared as 共享分类契约
    participant Plan as Plan
    participant Runtime as Runtime
    participant Compat as 历史分类适配
    participant Material as 物料状态

    Author->>Frontend: 源码及显式入口调用
    Frontend->>Frontend: 展开调用，保留原始 Span
    Frontend->>Validate: IR 与作用域分析
    Validate->>Validate: 通用参数名检查覆盖嵌套 content
    Validate->>Shared: 解析绑定，检查成员、枚举族与配对
    Shared-->>Validate: 分类结果或诊断
    Validate->>Validate: 同一来源的相同诊断只保留一次
    alt 静态校验失败
        Validate-->>Author: SEM / TYPE 诊断，阻止执行
    else 静态校验通过
        Validate->>Plan: 已校验 IR
        Plan->>Plan: 参数绑定，序列化枚举族与成员
        Plan->>Shared: 复核已知最终值
        alt 绑定值非法
            Plan-->>Author: PLAN 诊断，阻止执行
        else 已知值合法或需动态求值
            Plan->>Runtime: 可执行计划
            Runtime->>Runtime: 解码枚举，求动态值与别名快照
            alt 旧文本分类
                Runtime->>Compat: 规范化并保留原分类及推断属性
                Compat->>Shared: 检查规范化后的分类
            else 显式枚举分类
                Runtime->>Shared: 检查精确枚举族与配对
            end
            alt 最终分类非法
                Runtime-->>Author: MAT 诊断，拒绝受影响的写入
            else 最终分类合法
                Runtime->>Material: 写入 canonical 文本分类和属性
                Note over Runtime, Material: 显式 attrs 优先；role 可省略或自定义
            end
        end
    end
```

## 类图

```mermaid
classDiagram
    class OperationContractValidator {
        +validate_argument_names(call, node_id, allowed_args)
        +validate_call(call, node_id, operations)
    }
    class ConstructorValidator {
        +validate_define_content_call(call)
        +validate_alloc_container_call(call)
    }
    class SemanticValidator["validate/validator.py"]
    class SemanticValidator {
        +validate(ir, analysis)
        +deduplicate_diagnostics(diagnostics)
    }
    class BuiltinOperationSpecs["operation_specs.py"]
    ConstructorValidator ..> OperationContractValidator : 参数名检查
    OperationContractValidator ..> BuiltinOperationSpecs : 允许参数
    SemanticValidator ..> ConstructorValidator
    note for SemanticValidator "Span 对象身份确认共享来源<br/>坐标相同不代表同源；缺少来源时保守保留"

    class ContentArgumentResolver
    class ContentArgumentScope
    class DeferredContentEnum {
        +enum_type
    }
    ContentArgumentResolver ..> ContentArgumentScope
    ContentArgumentResolver ..> DeferredContentEnum : 控制流后保留枚举族
    ConstructorValidator ..> ContentArgumentResolver
    class SharedContentContracts["common/content_contracts.py"]
    class SharedContentContracts {
        +parse_content_classification(kind, type)
        +serialize_content_enum(value)
        +parse_serialized_content_enum(payload)
        +STANDARD_CONTENT_TYPES_BY_KIND_ENUM
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
    ContentClassification --> ContentKind
    ContentClassification --> ContentType
    SharedContentContracts ..> ContentClassification
    SharedContentContracts ..> ContainerKind
    ContentArgumentResolver ..> SharedContentContracts

    class PlanExpressionSerializer
    class ContentBoundary["pipeline/content_boundary.py"]
    class ContentBoundary {
        +read_bound_content_token(value, expected_enum)
        +resolve_bound_content_classification(kind, type)
        +resolve_bound_container_kind(value)
        +resolve_runtime_container_kind(value)
    }
    class BoundContentPlanValidator["plan/content_enums.py"]
    class RuntimeContent["runtime/material/container_content.py"]
    class LegacyContentTaxonomy["compat/content_taxonomy.py"]
    class NormalizedContentClassification {
        +kind : str
        +type : str
        +attrs
        +original_kind
        +original_type
        +classification : ContentClassification or None
    }
    PlanExpressionSerializer ..> SharedContentContracts : 序列化枚举身份
    BoundContentPlanValidator ..> ContentBoundary
    RuntimeContent ..> ContentBoundary
    ContentBoundary ..> SharedContentContracts
    ContentBoundary ..> LegacyContentTaxonomy : 仅旧输入
    LegacyContentTaxonomy ..> NormalizedContentClassification
    NormalizedContentClassification ..> ContentClassification : 合法分类提升

    class ContentReferenceChecker["conformance/content_contract.py"]
    class ContentReferenceChecker {
        +read_reference(root)
        +validate_snapshot(snapshot)
        +implementation_errors(contract)
        +requirement_hook_errors(contract, root)
    }
    class ReferenceRequirements["独立规范要求"]
    class ImplementationTestHooks["conformance/test_hooks.json"]
    class DerivedReferenceSnapshot["conformance/content_reference.json"]
    ContentReferenceChecker ..> ReferenceRequirements : 单向读取
    ContentReferenceChecker ..> DerivedReferenceSnapshot : 生成与核对
    ContentReferenceChecker ..> ImplementationTestHooks : 核对本仓库测试入口
    ContentReferenceChecker ..> SharedContentContracts : 验证符合性
    note for ContentReferenceChecker "工具和测试映射属于实现仓库<br/>不改变 reference 的语义权威或独立发布边界"
```

符合性工具与测试映射位于实现仓库的 `conformance/`。`test_hooks.json` 保存本实现的测试入口，reference 只提供要求和验收标准。

| 检查入口 | 用途 |
|---|---|
| `python -m conformance.content_contract --check` | 对照固定规范快照、实现及测试映射；实现 PR CI 使用此入口 |
| `python -m conformance.content_contract --reference-root ../culsma-reference --check` | 对照选定 reference 工作树；实现仓库的 Reference Conformance 手动工作流支持指定 revision |
| `python -m conformance.content_contract --reference-root ../culsma-reference --write` | 从已审阅规范重新生成派生快照；随后运行相应行为测试 |
