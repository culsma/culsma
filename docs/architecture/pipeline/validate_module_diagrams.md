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

## 1.0.8 Planned External Enum Contracts

Status: **domain type foundation implemented; DSL binding/lowering/runtime integration remains planned**. Coordination: [PM #110](https://github.com/culsma/culsma-pm/issues/110).
The three planned diagrams below use only Mermaid class, flowchart, and sequence syntax.
The class diagram is the primary change; flow and sequence describe the boundary integration.

| Boundary | Decision / invariant |
| --- | --- |
| Scope | First-group closed author-facing vocabularies only. Extensible classes, open attrs, and general internal discriminator cleanup follow separately. |
| Baseline | Branch `codex/1.0.8` was fast-forwarded to accepted RC work at `42b562b` before implementation; content contracts and source compatibility are reused. |
| Language ownership | The independent reference owns accepted member spellings, allowed values and compatibility semantics. Names below are proposals, not executable examples or a frozen reference contract. |
| Type identity | Validate enum family and member, including through aliases and protocol parameters. Equal serialized text does not make different enum families interchangeable. |
| Compatibility | Existing legal strings and bare tokens pass through a centralized source-compatibility adapter after normal binding resolution. A bound wrong-type value must not fall back to a token. |
| Downstream boundary | Carry validated enum identity through lowering and execution. Serialize using existing field-specific strings; reuse the output's semantic role for keep_source, not its tuple value. Historical-data decoding remains separate from source compatibility. |
| Behavior | Preserve operation-specific quantity membership, customized/schema_ref checks, plate geometry and supported capacity defaults, layout rules, schedule defaults and behavior. |
| Testability | New logical entry points are public and directly testable; acceptance also begins from complete DSL source. |

### Frozen First Delivery: Domain Types

The implemented first delivery owns closed enum definitions and pure parameter contracts in `culsma.domains`, independent of parser, pipeline, runtime and drivers. Existing pipeline imports of program output types remain aliases of the same classes. Source compatibility converts legacy text through `pipeline.compat.external_enums`; domain APIs accept exact enum families only. This delivery does not claim new DSL member syntax is executable: binding, lowering and runtime integration remain subsequent acceptance gates.

| Requirement | Invariant / diagnostic boundary | Test hook |
| --- | --- | --- |
| ENUM-DOMAIN | Each domain owns its members and immutable tables; readout allowed sets remain operation-specific | `tests/test_domain_enums.py` |
| ENUM-IDENTITY | Reject another enum family even when its string value compares equal; domain API raises TypeError, unsupported members raise ValueError | `tests/test_domain_enums.py` |
| ENUM-COMPAT | Only the source adapter accepts legacy strings; output roles decode using semantic_role; invalid strings fail | `tests/test_domain_enums.py` |
| ENUM-OWNERS | Existing registries derive vocabulary from domain contracts; existing public output imports retain class identity | `tests/test_domain_enums.py` |
| ENUM-EXTENSION | Closed enums cannot acquire extra members by subclassing. Extensible source classes need domain-specific contracts and separate metadata/execution capabilities; no empty catch-all program base is introduced | second delivery, pending extension declaration design |

| Domain owner | Implemented types / contracts | Existing consumer |
| --- | --- | --- |
| `domains/labware.py` | PlateFormat, geometry and capacity | plate selector compiler |
| `domains/separation.py` | Existing ProgramOutput families, DisruptionMethod, keep_source contract | program registry (backwards-compatible output imports) |
| `domains/readout.py` | ReadoutQuantity, per-operation contracts and schema requirement | readout vocabulary view |
| `domains/agitation.py` | AgitationMode including FLICK | agitation vocabulary view |
| `domains/fractionation.py` | DensityGradientAxis / Order | program registry |
| `domains/scheduling.py` | ScheduleMode and default | integration pending |

### Proposed Authoring Surface

Every expression in this table is **design-only**. The target values preserve the closed vocabularies; exact public names must be accepted in the owning reference before implementation.

| Parameter | Proposed new spelling | Members / restrictions | Current code owner |
| --- | --- | --- | --- |
| `plate.format` | `PlateFormat.WELL_96` | WELL_6, WELL_12, WELL_24, WELL_48, WELL_96, WELL_384; preserve explicit custom rows/cols rules | `domains/labware.py` → `compile/targets.py` |
| `centrifuge_program.keep_source` | `CentrifugeProgramOutput.PELLET` | Reuse existing SUPERNATANT / PELLET; do not create another output vocabulary | `program_registry.py` |
| `img.quantity` | `ReadoutQuantity.FLUORESCENCE` | UV_ABSORBANCE, FLUORESCENCE, COLORIMETRIC, CUSTOMIZED | `validate/statement_contracts.py` |
| `ecp.quantity` | `ReadoutQuantity.PH` | PH, CONDUCTIVITY, DISSOLVED_OXYGEN, ORP, CUSTOMIZED | `validate/statement_contracts.py` |
| `phy.quantity` | `ReadoutQuantity.TEMPERATURE` | TEMPERATURE, PRESSURE, FLOW_RATE, MASS, VOLUME, HUMIDITY, CURRENT, CUSTOMIZED | `validate/statement_contracts.py` |
| `agit.mode` | `AgitationMode.VORTEX` | VORTEX, INVERT, FLICK, SHAKE, STIR; FLICK preserved from the reconciled RC baseline | `validate/statement_contracts.py` |
| `disrupt_program.method` | `DisruptionMethod.SONICATION` | MECHANICAL, SONICATION, SHEAR_HOMOGENIZATION, HIGH_PRESSURE_DISRUPTION, BEAD_IMPACT | `program_registry.py` |
| `density_gradient_program.axis` | `DensityGradientAxis.DENSITY` | DENSITY | `program_registry.py` |
| `density_gradient_program.order` | `DensityGradientOrder.TOP_TO_BOTTOM` | TOP_TO_BOTTOM, BOTTOM_TO_TOP | `program_registry.py` |
| `schedule.mode` | `ScheduleMode.CONTINUOUS` | DISCRETE, CONTINUOUS; preserve omitted-mode default DISCRETE | `compile/schedule.py`, `plan/static_eval.py` |

### Planned Class Relationships — Primary Change

IMPLEMENTED marks delivered domain types; EXTEND marks pending pipeline integration; EXISTING marks a reusable output type. ExternalEnumContracts denotes `domains/contracts.py::EnumParameter`; SourceCompatibility denotes `pipeline/compat/external_enums.py`. Pipeline consumers and wire integration remain planned. No common extensible base class is introduced in this phase.

```mermaid
classDiagram
    class PlateFormat {
        <<IMPLEMENTED_ENUM>>
        WELL_6
        WELL_12
        WELL_24
        WELL_48
        WELL_96
        WELL_384
    }
    class CentrifugeProgramOutput {
        <<EXISTING_ENUM>>
        SUPERNATANT
        PELLET
    }
    class ReadoutQuantity {
        <<IMPLEMENTED_ENUM>>
        FLUORESCENCE
        PH
        TEMPERATURE
        CUSTOMIZED
    }
    class AgitationMode {
        <<IMPLEMENTED_ENUM>>
        VORTEX
        INVERT
        FLICK
        SHAKE
        STIR
    }
    class DisruptionMethod {
        <<IMPLEMENTED_ENUM>>
        MECHANICAL
        SONICATION
        SHEAR_HOMOGENIZATION
        HIGH_PRESSURE_DISRUPTION
        BEAD_IMPACT
    }
    class DensityGradientAxis {
        <<IMPLEMENTED_ENUM>>
        DENSITY
    }
    class DensityGradientOrder {
        <<IMPLEMENTED_ENUM>>
        TOP_TO_BOTTOM
        BOTTOM_TO_TOP
    }
    class ScheduleMode {
        <<IMPLEMENTED_ENUM>>
        DISCRETE
        CONTINUOUS
    }
    class ExternalEnumContracts {
        <<IMPLEMENTED_EnumParameter>>
        +enum_type
        +allowed_members
        +validate(value)
        +encode(value)
        +decode(value)
    }
    class SourceCompatibility {
        <<IMPLEMENTED_ADAPTER>>
        +resolve_legacy_enum(value, contract)
    }
    class ParameterConsumers {
        <<EXTEND>>
        +validate_domain_rules(value, context)
    }
    class WireCodec {
        <<EXTEND>>
        +encode_value(value, contract)
        +decode_value(payload, contract)
    }
    ExternalEnumContracts --> PlateFormat : plate.format
    ExternalEnumContracts --> CentrifugeProgramOutput : keep_source
    ExternalEnumContracts --> ReadoutQuantity : quantity per operation
    ExternalEnumContracts --> AgitationMode : agit.mode
    ExternalEnumContracts --> DisruptionMethod : disrupt.method
    ExternalEnumContracts --> DensityGradientAxis : density axis
    ExternalEnumContracts --> DensityGradientOrder : density order
    ExternalEnumContracts --> ScheduleMode : schedule.mode
    SourceCompatibility --> ExternalEnumContracts : produces validated members
    ParameterConsumers --> ExternalEnumContracts : checks identity and membership
    WireCodec --> ExternalEnumContracts : field-specific stable representation
    note for ReadoutQuantity "Representative members shown; full per-operation sets are in the table"
    note for AgitationMode "Domain owner: domains/agitation.py; RC FLICK member preserved"
```

### Planned Resolution Flow — Boundary Changes

This is a cross-stage value-resolution flow, not a change to the statement-handler lifecycle or a claim that semantic validation runs typecheck.

```mermaid
flowchart TB
    Source["DSL parameter expression"] --> Bind["Existing binding resolution<br/>including variables and protocol arguments"]
    Bind --> Shape{"Resolved value form"}
    Shape -->|enum member| Identity["NEW: check expected enum family"]
    Shape -->|legacy string or permitted bare token| Compat["EXTEND compat boundary:<br/>legacy spelling to expected enum member"]
    Shape -->|other type or unresolved binding| TypeError["Owning binding/type diagnostic"]
    Compat -->|recognized| Identity
    Compat -->|unknown| ValueError["Semantic value diagnostic"]
    Identity -->|wrong family| TypeError
    Identity -->|correct family| Allowed["NEW: check operation-specific members"]
    Allowed -->|not allowed| ValueError
    Allowed -->|allowed| Domain["Existing domain checks:<br/>schema_ref, layout, scheduling rules"]
    Domain -->|valid| Lower["EXTEND lowering and execution:<br/>preserve typed identity"]
    Lower --> Wire["Boundary codec:<br/>existing serialized field values"]
    classDef planned fill:#fff3cd,stroke:#b7791f,stroke-width:2px
    class Identity,Compat,Allowed,Lower planned
```

### Planned Call Sequence — Integration and Verification

Participants denote responsibilities across the frontend and execution pipeline; detailed diagnostic IDs and stage hooks are frozen before code changes. Each earliest-decidable failure terminates this value's path without duplicate downstream diagnostics.

```mermaid
sequenceDiagram
    actor Author
    participant Frontend as Parser and binding
    participant Types as Typecheck
    participant Compat as Source compat adapter
    participant Semantic as Semantic contracts
    participant Exec as Plan and runtime
    participant Codec as Serialization boundary
    Author->>Frontend: Parameter expression / alias / protocol argument
    Frontend->>Types: Resolved expression and expected enum family
    alt Proposed enum member
        Types->>Types: Check enum-family identity
        Types->>Semantic: Correctly typed member
    else Compatible legacy text or bare token
        Types->>Compat: Resolve permitted legacy input in field context
        Compat->>Semantic: Canonical member or value diagnostic
    end
    Semantic->>Semantic: Allowed members and dependent domain rules
    Semantic->>Exec: Validated value with enum identity
    Exec->>Codec: Result containing typed values
    Codec-->>Author: Stable field-specific serialized values
    Note over Frontend,Codec: NEW tests: complete-source old/new equivalence and boundary round trips
```

### Delivery Order and Acceptance Hooks

| Order / requirement | Deliverable | Planned complete-source test hook |
| --- | --- | --- |
| 0 / ENUM-BASELINE | RC baseline reconciled; freeze source reference/call contracts and exact diagnostic ownership before DSL integration | `test_external_enum_reference_conformance` |
| 1 / ENUM-PLATE | Plate format, geometry/selection and compatibility | `test_plate_format_enum_frontend_equivalence` |
| 2 / ENUM-OUTPUT | keep_source reuses centrifuge outputs, rejects other output families | `test_keep_source_enum_frontend_contract` |
| 3 / ENUM-READOUT | Readout enums with per-operation subsets and customized schema rules | `test_readout_quantity_enum_frontend_contract` |
| 4 / ENUM-MODES | Agitation, disruption, density axis/order and scheduling | `test_closed_mode_enums_frontend_contract` |
| Each / ENUM-IDENTITY | Direct members, aliases, protocol parameters, wrong families/members and binding shadowing | `test_external_enum_binding_and_diagnostics` |
| Each / ENUM-WIRE | Old/new execution equivalence, stable serialized values and historical-data decoding | `test_external_enum_runtime_roundtrip` |

Hooks above are planned, not existing passing tests. Wrong value shape/family belongs to typecheck; unresolved references belong to binding; disallowed members and dependent rules belong to semantic validation. Member lookup errors belong to the first stage able to resolve that enum namespace. Reuse existing diagnostic identities where applicable and settle exact mappings before implementation. Promote accepted language rules into existing owning reference sections without code dependencies.
