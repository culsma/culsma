# BPL (Biology Programming Language) 语法参考手册

> 版本: v2.5
> 更新日期: 2025-12-29

---

## 目录

1. [概述](#1-概述)
2. [程序结构](#2-程序结构)
3. [数据类型与单位系统](#3-数据类型与单位系统)
4. [声明语法](#4-声明语法)
5. [核心操作](#5-核心操作)
6. [控制流结构](#6-控制流结构)
7. [注解与合规性](#7-注解与合规性)
8. [状态管理](#8-状态管理)
9. [错误处理](#9-错误处理)
10. [完整示例](#10-完整示例)

---

## 1. 概述

### 1.1 什么是BPL？

BPL (Biology Programming Language) 是一种专为生物实验设计的领域特定语言(DSL)。它在编译器级别内置了：

- **物理量纲验证** - 编译时检查单位一致性
- **状态追踪** - 容器、体积、内容物的自动追踪
- **合规性支持** - 原生支持 GxP、21 CFR Part 11 等法规要求
- **混合自动化** - 无缝集成人工操作与机器人自动化步骤

### 1.2 设计原则

| 原则 | 说明 |
|------|------|
| 生物学感知 | 内置分子量、浓度推导、物理形态约束 |
| 类型安全 | 编译时验证物理约束（固体/液体操作规则） |
| 可追溯 | 每个状态变化都有明确的 StateDelta 记录 |
| 可迁移 | 抽象意图层可降级到不同硬件平台 |

---

## 2. 程序结构

### 2.1 顶层结构

```
Program → Declaration*

Declaration → Import
            | Module
            | Protocol
            | Reagent
            | Stock
            | Labware
            | DeckModel
            | Target
            | Resource
            | Type
            | Function
            | Intent
            | Primitive
            | Recovery
            | Invariant
            | PCRProfile
```

### 2.2 导入语法

```bpl
// 完整导入
import stdlib.reagents version "1.0"

// 别名导入
import stdlib.labware as labware

// 选择性导入
from stdlib.reagents import NaCl, Water, Ethanol
```

### 2.3 模块定义

```bpl
module MyModule {
    // 模块内的声明
    reagent CustomReagent { ... }
    protocol CustomProtocol { ... }
}
```

---

## 3. 数据类型与单位系统

### 3.1 原始量纲类型

| 类型 | 说明 | 支持的单位 |
|------|------|-----------|
| `Mass` | 质量 | `kg`, `g`, `mg`, `ug`, `ng`, `pg` |
| `Volume` | 体积 | `L`, `mL`, `uL`, `nL` |
| `Temperature` | 温度 | `degC`, `K` |
| `Time` | 时间 | `d`, `h`, `min`, `s`, `ms` |
| `Speed` | 速度 | `rpm`, `rcf` |
| `Length` | 长度 | `m`, `cm`, `mm`, `um`, `nm`, `bp`, `kb`, `Mb` |
| `Pressure` | 压力 | `atm`, `psi`, `kPa`, `bar` |
| `Moles` | 摩尔数 | `mol`, `mmol`, `umol`, `nmol`, `pmol` |
| `Percentage` | 百分比 | `%`, `percent` |
| `FoldFactor` | 稀释倍数 | `X` (如 `1000X`, `50X`) |

### 3.2 浓度类型

BPL 支持两种浓度表达方式，并能在已知分子量时自动转换：

```bpl
// 摩尔浓度
type MolarConcentration = Number with (M | mM | uM | nM | pM)

// 质量浓度
type MassConcentration = Number with (g/L | mg/mL | ug/mL | ng/uL)

// 自动转换示例
// 58.44 g NaCl / 1 L given MW=58.44 g/mol → 1 M
```

### 3.3 复合单位

```bpl
// 流速
uL/s, mL/min

// 浓度
g/L, mg/mL, mol/L, mmol/L

// 分子量
g/mol

// 温度变化率
degC/min
```

### 3.4 单位运算规则

```bpl
// 同量纲加减
10 mL + 5 mL       → 15 mL
10 mL - 3 mL       → 7 mL

// 不同量纲乘除（生成推导单位）
10 g / 100 mL      → 100 mg/mL
50 uL / 10 s       → 5 uL/s

// 同量纲除法（无量纲结果）
(10 mL) / (5 mL)   → 2.0 (Number)

// 显式单位转换
100 mL.to(uL)      → 100000 uL
1 M.to(mM)         → 1000 mM
```

### 3.5 容器引用类型

```bpl
type Source = ReagentRef | StockRef | ContainerRef | WellRef | WellSetRef

type Destination = ContainerRef | WellRef | WellSetRef

type WellRef = { plate: String, well_id: WellID }      // 如 "A1", "H12"
type WellSetRef = { plate: String, wells: List<WellID> }
```

### 3.6 复合类型

```bpl
// 列表类型
type ListType<T>

// 映射类型
type MapType<K, V>

// 记录类型（积类型）
type ProductType = { field1: Type1, field2: Type2 }

// 枚举类型（和类型）
type SumType = Variant1 { fields } | Variant2 { fields }
```

### 3.7 物理形态约束

```bpl
type PhysicalForm = Solid | Liquid | Gas

// 编译时约束检查
add(NaCl, mass: 10 g, to: beaker)        // ✓ OK (固体按质量添加)
add(NaCl, volume: 10 mL, to: beaker)     // ✗ ERROR: NaCl是固体
add(Water, volume: 100 mL, to: beaker)   // ✓ OK (液体按体积添加)
```

---

## 4. 声明语法

### 4.1 协议声明 (protocol)

协议是BPL的核心结构，定义一个完整的实验流程。

```bpl
protocol ProtocolName(param1: Type1, param2: Type2 = default_value) {
    @protocol_setting: value

    statement*
}
```

**示例：**

```bpl
protocol TransformationAssay(dna: DNA, host: Strain) {
    @compliance(GxP)
    @error_policy: { default: Stop }

    let culture = prepare(host)
    transfer(from: dna, to: culture, volume: 100 uL)
    incubate(container: culture, temperature: 42 degC, duration: 30 s)
}
```

### 4.2 试剂声明 (reagent)

```bpl
reagent ReagentName {
    physical_form: Solid | Liquid | Gas
    MW: Quantity                          // 分子量 (可选)
    description: String                   // 描述 (可选)
    cas_number: String                    // CAS号 (可选)
    hazard_class: HazardClass            // 危险等级 (可选)
}
```

**示例：**

```bpl
reagent NaCl {
    physical_form: Solid
    MW: 58.44 g/mol
    description: "Sodium chloride"
    cas_number: "7647-14-5"
}

reagent Ethanol {
    physical_form: Liquid
    MW: 46.07 g/mol
    description: "Ethyl alcohol"
    hazard_class: Flammable
}
```

### 4.3 库存溶液声明 (stock)

```bpl
stock StockName {
    reagent: ReagentName
    concentration: Quantity
    solvent: ReagentName
    fold: Number X                        // 稀释倍数 (可选)
}
```

**示例：**

```bpl
stock NaCl_1M {
    reagent: NaCl
    concentration: 1 M
    solvent: Water
}

stock Kanamycin_1000X {
    reagent: Kanamycin
    concentration: 50 mg/mL
    solvent: Water
    fold: 1000X
}
```

**Fold因子验证（v2.4+）：**

```bpl
add(Kanamycin_1000X, fold: 1000, to: media)   // ✓ 倍数匹配
add(Kanamycin_1000X, fold: 500, to: media)    // ✗ 编译错误：倍数不匹配
```

### 4.4 实验器材声明 (labware)

```bpl
labware LabwareName {
    footprint: SBS_Standard | SBS_Half | Custom
    well_count: Integer
    well_volume: Quantity
    category: Plate_96 | Plate_384 | TipRack | Reservoir | Tube
    barcode: String                       // (可选)
    set_identifier: String               // (可选)
}
```

**示例：**

```bpl
labware DeepWellPlate_96 {
    footprint: SBS_Standard
    well_count: 96
    well_volume: 2.2 mL
    category: Plate_96
}

labware PCRPlate_384 {
    footprint: SBS_Standard
    well_count: 384
    well_volume: 50 uL
    category: Plate_384
}
```

### 4.5 器材类别声明 (labware_category)

```bpl
labware_category CategoryName {
    compatible_with: [Footprint1, Footprint2]
    default_lid: LidType
}
```

### 4.6 甲板模型声明 (deck_model)

```bpl
deck_model DeckModelName {
    positions: [
        { id: "P1", accepts: [SBS_Standard], coordinates: {x: 0, y: 0, z: 0}, is_waste: false }
        { id: "P2", accepts: [SBS_Standard], coordinates: {x: 100, y: 0, z: 0}, is_waste: false }
        { id: "Waste", accepts: [Reservoir], is_waste: true }
    ]
}
```

### 4.7 目标/执行环境声明 (target)

```bpl
target TargetName {
    capabilities: [cap1, cap2, cap3, ...]
    NOT: [unsupported_cap1, unsupported_cap2]
}
```

**示例：**

```bpl
target Biomek_i7 {
    capabilities: [aspirate, dispense, pick_tips, drop_tips, pipette_mix, incubate]
    NOT: [vortex, weigh, seal_plate]
}

target Manual_Operator {
    capabilities: [all]
}
```

### 4.8 资源声明 (resource) - v2.4+

用于声明共享资源（如离心机、读板器等）的并发控制。

```bpl
resource ResourceName {
    capacity: Integer                     // 并发使用数
    booking_required: Boolean            // 是否需要预订
    cooldown: Quantity                   // 冷却时间 (可选)
    min_booking_duration: Quantity       // 最小预订时间 (可选)
}
```

**示例：**

```bpl
resource Centrifuge_1 {
    capacity: 1
    booking_required: true
    cooldown: 30 s
    min_booking_duration: 15 min
}

resource PlateReader_1 {
    capacity: 1
    booking_required: true
}
```

### 4.9 类型别名声明 (type)

```bpl
type TypeName = TypeExpression
```

**示例：**

```bpl
type Concentration = MassConcentration | MolarConcentration
type WellList = List<WellRef>
type StockSolution = { reagent: ReagentRef, concentration: Concentration, solvent: ReagentRef }
```

### 4.10 函数声明 (function)

```bpl
function FunctionName(param1: Type1, param2: Type2) -> ReturnType {
    statement*
    return expression
}
```

**示例：**

```bpl
function calculate_dilution(stock_conc: Concentration, target_conc: Concentration, final_volume: Volume) -> Volume {
    return (target_conc * final_volume) / stock_conc
}

function get_well_count(plate: Labware) -> Integer {
    return plate.well_count
}
```

### 4.11 意图声明 (intent)

高层抽象操作，不含具体实现，由编译器降级到具体原语。

```bpl
intent IntentName(params...) -> ReturnType
```

**示例：**

```bpl
intent add(source: Source, to: Destination, volume: Volume?) -> StateTransition
intent transfer(from: Source, to: Destination, volume: Volume) -> StateTransition
intent mix(container: Container, volume: Volume, repetitions: Integer) -> StateTransition
intent incubate(container: Container, temperature: Temperature, duration: Time) -> StateTransition
```

### 4.12 原始操作声明 (primitive)

最底层的硬件操作，直接映射到设备指令。

```bpl
primitive PrimitiveName(params...) -> ReturnType
```

**示例：**

```bpl
primitive aspirate(from: WellRef | ContainerRef, volume: Volume, speed: VolumeRate)
primitive dispense(to: WellRef | ContainerRef, volume: Volume, speed: VolumeRate)
primitive pick_tips(tip_type: TipType, count: Integer, from: TipRackRef)
primitive drop_tips(to: WasteRef)
primitive move_to(position: Position, speed: Speed)
```

### 4.13 恢复程序声明 (recovery) - v2.4+

定义错误发生时的恢复流程。

```bpl
recovery RecoveryName {
    @for_error: ErrorType
    statement*
}
```

**示例：**

```bpl
recovery TipClogRecovery {
    @for_error: TipClog
    drop_tips(to: Waste)
    pick_tips(type: same_as_before, count: same_as_before)
}

recovery LiquidNotFoundRecovery {
    @for_error: LiquidNotFound
    manual(instruction: "Check source container and refill if needed")
}
```

### 4.14 不变量声明 (invariant) - v2.4+

定义运行时必须满足的条件。

```bpl
invariant "InvariantName" {
    check: Expression
    after: [step1, step2, ...]
    on_violation: Action
}
```

**示例：**

```bpl
invariant "cell_viability" {
    check: cells.viability > 0.9
    after: [centrifuge, resuspend]
    on_violation: AlertAndContinue { timeout: 5 min }
}

invariant "temperature_range" {
    check: incubator.temperature >= 36 degC && incubator.temperature <= 38 degC
    after: [incubate]
    on_violation: Stop
}
```

### 4.15 PCR轮廓声明 (pcr_profile)

定义PCR温度循环程序。

```bpl
pcr_profile ProfileName {
    initial: Temperature for Time
    cycles: Integer {
        denature: Temperature for Time
        anneal: Temperature for Time
        extend: Temperature for Time
    }
    final: Temperature for Time
    hold: Temperature
    lid_temp: Temperature
}
```

**示例：**

```bpl
pcr_profile Q5_Standard {
    initial: 98 degC for 30 s
    cycles: 30 {
        denature: 98 degC for 10 s
        anneal: 60 degC for 20 s
        extend: 72 degC for 30 s
    }
    final: 72 degC for 2 min
    hold: 4 degC
    lid_temp: 105 degC
}

pcr_profile TouchDown_PCR {
    initial: 95 degC for 3 min
    cycles: 10 {
        denature: 95 degC for 30 s
        anneal: 65 degC for 30 s    // 每循环降低0.5°C
        extend: 72 degC for 1 min
    }
    cycles: 25 {
        denature: 95 degC for 30 s
        anneal: 55 degC for 30 s
        extend: 72 degC for 1 min
    }
    final: 72 degC for 5 min
    hold: 4 degC
    lid_temp: 105 degC
}
```

---

## 5. 核心操作

### 5.1 液体转移操作

#### transfer - 液体转移

```bpl
transfer(
    from: Source,
    to: Destination,
    volume: Volume,
    distribution: String?    // "all" | "zip" | "broadcast"
)
```

**示例：**

```bpl
// 单点转移
transfer(from: source_tube, to: dest_tube, volume: 100.0 uL)

// 批量转移到所有孔
transfer(from: reagent_reservoir, to: plate_96, volume: 50.0 uL, distribution: "all")

// 1:1 对应转移
transfer(from: source_plate[A1:H1], to: dest_plate[A1:H1], volume: 10.0 uL)
```

#### add - 添加试剂

```bpl
add(
    source: Source,
    to: Destination,
    volume: Volume?,
    mass: Mass?,
    to_concentration: Concentration?,
    fold: Integer?
)
```

**示例：**

```bpl
// 按体积添加
add(Water, to: beaker, volume: 100.0 mL)

// 按质量添加（固体）
add(NaCl, to: beaker, mass: 5.84 g)

// 按最终浓度添加
add(NaCl_1M, to_concentration: 100 mM, to: reaction_tube)

// 按稀释倍数添加
add(Kanamycin_1000X, fold: 1000, to: culture_medium)
```

#### distribute - 分配

```bpl
distribute(
    from: Source,
    to: Destination,
    volume: Volume
)
```

**示例：**

```bpl
// 从一个源分配到多个目标
distribute(from: master_mix, to: pcr_plate[A1:H12], volume: 20.0 uL)
```

### 5.2 混合操作

#### mix - 混匀

```bpl
mix(
    container: Container,
    volume: Volume,
    repetitions: Integer,
    distribution: String?
)
```

**示例：**

```bpl
mix(container: reaction_tube, volume: 50.0 uL, repetitions: 5)
mix(container: plate_96, volume: 100.0 uL, repetitions: 3, distribution: "all")
```

#### vortex - 涡旋

```bpl
vortex(
    container: Container,
    duration: Time,
    speed: Speed?
)
```

### 5.3 温控操作

#### incubate - 孵育

```bpl
incubate(
    container: Container,
    temperature: Temperature,
    duration: Time,
    shaker_speed: Speed?
)
```

**示例：**

```bpl
// 静态孵育
incubate(container: plate, temperature: 37 degC, duration: 1 h)

// 带摇床孵育
incubate(container: flask, temperature: 30 degC, duration: 24 h, shaker_speed: 220 rpm)

// 冰上孵育
incubate(container: tube, temperature: 0 degC, duration: 5 min)
```

#### thermocycle - 热循环

```bpl
thermocycle(
    container: Container,
    profile: PCRProfile
)
```

**示例：**

```bpl
thermocycle(container: pcr_plate, profile: Q5_Standard)
```

### 5.4 分离操作

#### centrifuge - 离心

```bpl
centrifuge(
    container: Container,
    speed: Speed,
    duration: Time,
    temperature: Temperature?
)
```

**示例：**

```bpl
centrifuge(container: tubes, speed: 3000 rpm, duration: 10 min)
centrifuge(container: plate, speed: 1000 rcf, duration: 5 min, temperature: 4 degC)
```

### 5.5 检测操作

#### measure - 测量

```bpl
measure(
    container: Container,
    property: MeasurementProperty
)
```

**示例：**

```bpl
// 吸光度测量
measure(plate, property: Absorbance { wavelength: 600 nm })
measure(plate, property: Absorbance { wavelength: 260 nm, reference: 320 nm })

// 荧光测量
measure(plate, property: Fluorescence { excitation: 485 nm, emission: 520 nm })

// 发光测量
measure(plate, property: Luminescence)
```

### 5.6 密封操作

#### seal - 封板

```bpl
seal(container: Container, seal_type: SealType?)
```

#### unseal - 开封

```bpl
unseal(container: Container)
```

### 5.7 存储操作

#### store - 存储

```bpl
store(container: Container, temperature: Temperature, location: String?)
```

**示例：**

```bpl
store(container: sample_plate, temperature: -80 degC)
store(container: reagent, temperature: 4 degC, location: "Cold Room A")
```

### 5.8 人工操作

#### manual - 人工步骤

```bpl
manual(
    instruction: String,
    affects: List<Container>?,
    state_effects: StateDelta?,
    record: List<Field>?
)
```

**示例：**

```bpl
// 简单指令
manual(instruction: "Visually inspect the plate for contamination")

// 带状态效果
manual(
    instruction: "Carefully decant supernatant",
    affects: [tube],
    state_effects: StateDelta {
        tube: { volume_change: -900.0 uL }
    }
)

// 带数据记录
manual(
    instruction: "Weigh the sample and record the mass",
    record: [
        NumberField { name: "mass_g", unit: g, required: true }
    ]
)
```

### 5.9 工作列表操作 (v2.5)

#### stamp - 印章转移

```bpl
stamp(from: Plate, to: Plate, volume: Volume)
```

#### cherrypick - 精准挑选

```bpl
cherrypick(
    from: WellSetRef,
    to: WellSetRef,
    volume: Volume
)
```

#### serial_dilute - 梯度稀释

```bpl
serial_dilute(
    source: Container,
    destinations: List<Container>,
    volume: Volume,
    steps: Integer
)
```

---

## 6. 控制流结构

### 6.1 条件语句

```bpl
if condition {
    statement*
} else if condition {
    statement*
} else {
    statement*
}
```

**示例：**

```bpl
if od > 0.6 {
    stop_incubation()
} else if od > 0.4 {
    adjust_temperature(37 degC)
} else {
    continue_incubation()
}
```

### 6.2 For循环

```bpl
for variable in iterable {
    statement*
}
```

**示例：**

```bpl
for well in plate.wells(All) {
    transfer(from: source, to: well, volume: 50.0 uL)
}

for i in 1..8 {
    transfer(from: samples[i], to: dest[i], volume: 100.0 uL)
}
```

### 6.3 While循环

```bpl
while condition {
    statement*
}
```

**示例：**

```bpl
while od < 0.6 {
    incubate(container: culture, temperature: 37 degC, duration: 30 min)
    let od = measure(culture, property: Absorbance { wavelength: 600 nm })
}
```

### 6.4 并行执行块

```bpl
parallel {
    sequence {
        statement*
    }
    sequence {
        statement*
    }
}
```

**示例：**

```bpl
// 并行孵育两个板
parallel {
    sequence {
        incubate(container: plate_a, temperature: 37 degC, duration: 30 min)
    }
    sequence {
        incubate(container: plate_b, temperature: 37 degC, duration: 30 min)
    }
}

// 并行准备和检测
parallel {
    sequence {
        transfer(from: reagent_a, to: plate_1, volume: 100.0 uL)
        incubate(container: plate_1, temperature: 37 degC, duration: 1 h)
    }
    sequence {
        transfer(from: reagent_b, to: plate_2, volume: 100.0 uL)
        incubate(container: plate_2, temperature: 37 degC, duration: 1 h)
    }
}
```

### 6.5 变量绑定

```bpl
let variable = expression
let variable: Type = expression
```

**示例：**

```bpl
let volume_needed = 1000.0 uL
let target_concentration: Concentration = 1 M
let result = measure(plate, property: Absorbance { wavelength: 600 nm })
```

### 6.6 集合语义

BPL支持三种集合操作语义：

| 语义 | 说明 | 示例 |
|------|------|------|
| `Zip` | 1:1映射（默认） | 8个源→8个目标 |
| `Broadcast` | 1:N复制 | 1个源→N个目标 |
| `Product` | 笛卡尔积 | M×N个转移 |

```bpl
// Zip语义（默认）
transfer(from: sources[A1:H1], to: dests[A1:H1], volume: 50.0 uL)

// Broadcast语义
distribute(from: source, to: dests[A1:H12], volume: 100.0 uL)

// 显式指定语义
@semantics(Product)
transfer(from: rows[A1:A8], to: cols[A1:A12], volume: 10.0 uL)
```

---

## 7. 注解与合规性

### 7.1 注解语法

```bpl
@annotation_name
@annotation_name(arg1: value1, arg2: value2)
@annotation_name: value
```

### 7.2 步骤注解

```bpl
@step(id: "step_id", description: "Step description")
@checkpoint("Checkpoint name")
```

**示例：**

```bpl
@step(id: "S1", description: "Initial setup")
@checkpoint("Reagents prepared")
manual(instruction: "Prepare all reagents on ice")

@step(id: "S2", description: "Heat shock transformation")
@checkpoint("Before heat shock")
incubate(container: cells, temperature: 42 degC, duration: 45 s)
```

### 7.3 合规性注解

```bpl
// 协议级合规性
@compliance(GxP)
@compliance(GLP)
@compliance(GMP)

// 上下文设置
@context(Research)
@context(GLP)
@context(GMP)

// 签名要求
@witness_required
@electronic_signatures(Part11)

// 步骤关键性标记
@step(critical)
```

**示例：**

```bpl
@compliance(GMP)
protocol CriticalAssay {
    @step(critical)
    @witness_required
    manual(instruction: "Verify lot numbers and sign off")

    @electronic_signatures(Part11)
    transfer(from: reference_sample, to: control_plate, volume: 50.0 uL)
}
```

### 7.4 合规性上下文规则

| 上下文 | 要求 |
|--------|------|
| Research | 最小合规要求，主要用于探索性实验 |
| GLP | 需要校准验证，数据完整性 |
| GMP | 需要完全验证、电子签名、审计追踪 |

```bpl
@context: GMP
protocol GMPAssay {
    // 在GMP上下文中，所有状态变化需要Verified级别的信任
    @step(critical)
    manual(
        instruction: "Weigh and record sample mass",
        record: [NumberField { name: "mass_g", unit: g, required: true }]
    )
}
```

---

## 8. 状态管理

### 8.1 StateDelta 结构

StateDelta用于声明实验步骤对系统状态的影响。

```bpl
state_effects: StateDelta {
    container_name: {
        volume: Quantity,           // 当前体积
        capacity: Quantity,         // 最大容量
        volume_change: Quantity?,   // 体积变化量
        contents: List<Reagent>?,   // 内容物列表
        contents_change: {          // 内容物变化
            add: List<Reagent>?,
            remove: List<Reagent>?,
            retain: List<Reagent>?
        }?
    }
}
```

**示例：**

```bpl
// 初始化状态
manual(instruction: "Setup containers", state_effects: StateDelta {
    source_tube: { volume: 1000.0 uL, capacity: 1500.0 uL }
    dest_tube: { volume: 0.0 uL, capacity: 1500.0 uL }
    reagent_stock: { volume: 5000.0 uL, capacity: 10000.0 uL }
})

// 描述状态变化
manual(
    instruction: "Decant supernatant",
    state_effects: StateDelta {
        tube: {
            volume_change: -900.0 uL,
            contents_change: { remove: [Supernatant], retain: [Pellet] }
        }
    }
)
```

### 8.2 孔板状态

```bpl
wells_modified: [
    {
        well: plate["A1"],
        volume: 50.0 uL,
        contents: [PBS, Cells]
    },
    {
        well: plate["A2"],
        volume: 50.0 uL,
        contents: [PBS, Cells]
    }
]
```

### 8.3 信任级别 (v2.4)

| 级别 | 说明 | 适用上下文 |
|------|------|-----------|
| `Declared` | 用户/编译器声明，未验证 | Research |
| `Calibrated` | 传感器/仪器验证 | GLP |
| `Verified` | 校准+操作员签名 | GMP |

```bpl
type StateTrustLevel = Declared | Calibrated | Verified

// GMP要求
if protocol.context == GMP {
    MINIMUM_TRUST: Verified
}
```

---

## 9. 错误处理

### 9.1 错误类型

```bpl
// 移液错误
type PipetteError = TipClog | LiquidNotFound | OverAspiration | TipPickupFail

// 运动错误
type MotionError = CollisionDetected | PositionUnreachable | LabwareNotFound

// 传感器错误
type SensorError = ReaderTimeout | TemperatureOutOfRange | LiquidSenseFail

// 人工操作错误
type HumanError = ConfirmationTimeout | InvalidDataEntry
```

### 9.2 错误策略

```bpl
type ErrorPolicy =
    | Stop                                              // 立即停止
    | Retry { max: Integer, delay: Time?, with_fresh_tip: Boolean? }
    | Skip { log_reason: Boolean, continue_batch: Boolean }
    | AlertAndContinue { timeout: Time, default_action: Stop | Skip }
    | Fallback { alternative: Action }
    | Escalate { to: UserRole, timeout: Time }
```

### 9.3 步骤级错误处理

```bpl
@on_error(Stop)
transfer(from: precious_sample, to: dest, volume: 50.0 uL)

@on_error(match: TipClog, action: Retry { max: 2 })
@on_error(match: LiquidNotFound, action: Skip { log_reason: true })
transfer(from: plate_a, to: plate_b, volume: 100.0 uL)

// 带恢复程序
@on_error(match: TipClog, action: Retry { max: 2, recovery: TipClogRecovery })
aspirate(from: source, volume: 100.0 uL)
```

### 9.4 协议级错误策略

```bpl
protocol RobustTransfer {
    @error_policy: {
        TipClog: Retry { max: 3, delay: 5 s, with_fresh_tip: true },
        LiquidNotFound: AlertAndContinue { timeout: 60 s, default_action: Skip },
        CollisionDetected: Stop,
        default: Stop
    }

    // 协议内容...
}
```

### 9.5 批量错误处理

```bpl
@batch_error_policy: CollectAndReport {
    max_failures: 10,
    failure_threshold: 0.1,      // 10%失败率阈值
    report_at_end: true
}
transfer(from: plate_a.wells(All), to: plate_b.wells(All), volume: 100.0 uL)
```

### 9.6 检查点与断言

```bpl
// 状态快照（可恢复点）
@checkpoint("Before critical step")
measure(plate, property: Absorbance)

// 运行时断言
@assert(cells.viability > 0.95, "Cell viability too low")
incubate(container: culture, temperature: 37 degC, duration: 4 h)
```

---

## 10. 完整示例

### 10.1 细菌转化协议

```bpl
protocol BacterialTransformation {
    @compliance(GLP)
    @error_policy: { default: Stop }

    manual(instruction: "Prepare competent cells, plasmid DNA, and recovery medium", state_effects: StateDelta {
        competent_cells: { volume: 200.0 uL, capacity: 500.0 uL }
        plasmid_dna: { volume: 20.0 uL, capacity: 50.0 uL }
        soc_medium: { volume: 2000.0 uL, capacity: 5000.0 uL }
        transformation_tube: { volume: 0.0 uL, capacity: 2000.0 uL }
        lb_plate: { volume: 0.0 uL, capacity: 1000.0 uL }
    })

    @step(id: "S1", description: "Add competent cells")
    @checkpoint("Cells added")
    transfer(from: competent_cells, to: transformation_tube, volume: 50.0 uL)

    @step(id: "S2", description: "Add plasmid DNA")
    transfer(from: plasmid_dna, to: transformation_tube, volume: 2.0 uL)

    @step(id: "S3", description: "Incubate on ice")
    incubate(container: transformation_tube, temperature: 0 degC, duration: 30 min)

    @step(id: "S4", description: "Heat shock")
    @checkpoint("Before heat shock")
    @step(critical)
    incubate(container: transformation_tube, temperature: 42 degC, duration: 45 s)

    @step(id: "S5", description: "Recovery on ice")
    incubate(container: transformation_tube, temperature: 0 degC, duration: 2 min)

    @step(id: "S6", description: "Add recovery medium")
    transfer(from: soc_medium, to: transformation_tube, volume: 950.0 uL)

    @step(id: "S7", description: "Recovery incubation")
    incubate(container: transformation_tube, temperature: 37 degC, duration: 60 min)

    @step(id: "S8", description: "Plate transformants")
    transfer(from: transformation_tube, to: lb_plate, volume: 100.0 uL)

    @step(id: "S9", description: "Overnight incubation")
    incubate(container: lb_plate, temperature: 37 degC, duration: 16 h)
}
```

### 10.2 高通量PCR设置

```bpl
pcr_profile Standard_PCR {
    initial: 98 degC for 30 s
    cycles: 30 {
        denature: 98 degC for 10 s
        anneal: 60 degC for 20 s
        extend: 72 degC for 30 s
    }
    final: 72 degC for 2 min
    hold: 4 degC
    lid_temp: 105 degC
}

protocol HighThroughputPCR {
    manual(instruction: "Setup PCR reagents and template plate", state_effects: StateDelta {
        master_mix_stock: { volume: 2000.0 uL, capacity: 5000.0 uL }
        primer_fwd_stock: { volume: 500.0 uL, capacity: 1000.0 uL }
        primer_rev_stock: { volume: 500.0 uL, capacity: 1000.0 uL }
        template_plate: { volume: 9600.0 uL, capacity: 20000.0 uL }
        water_stock: { volume: 5000.0 uL, capacity: 10000.0 uL }
        pcr_plate: { volume: 0.0 uL, capacity: 20000.0 uL }
    })

    @step(id: "setup", description: "Distribute PCR components")
    @checkpoint("Begin PCR setup")

    // 分配Master Mix到所有孔
    distribute(from: master_mix_stock, to: pcr_plate, volume: 12.5 uL)

    // 分配引物
    parallel {
        sequence {
            distribute(from: primer_fwd_stock, to: pcr_plate, volume: 1.0 uL)
        }
        sequence {
            distribute(from: primer_rev_stock, to: pcr_plate, volume: 1.0 uL)
        }
    }

    // 添加模板
    @step(id: "template", description: "Add template DNA")
    stamp(from: template_plate, to: pcr_plate, volume: 2.0 uL)

    // 补水
    distribute(from: water_stock, to: pcr_plate, volume: 8.5 uL)

    // 混匀
    mix(container: pcr_plate, volume: 10.0 uL, repetitions: 3, distribution: "all")

    // 封板
    seal(container: pcr_plate)

    @step(id: "thermocycle", description: "Run PCR")
    @checkpoint("Before thermocycling")
    thermocycle(container: pcr_plate, profile: Standard_PCR)

    @checkpoint("PCR complete")
}
```

### 10.3 蛋白表达与纯化

```bpl
resource Centrifuge_Main {
    capacity: 1
    booking_required: true
    min_booking_duration: 10 min
}

resource Sonicator {
    capacity: 1
    booking_required: true
    cooldown: 5 min
}

protocol ProteinExpressionPurification {
    @compliance(GLP)

    manual(instruction: "Prepare culture, induction reagents, and purification buffers", state_effects: StateDelta {
        culture_flask: { volume: 500.0 mL, capacity: 1000.0 mL }
        iptg_stock: { volume: 1.0 mL, capacity: 5.0 mL }
        lysis_buffer: { volume: 100.0 mL, capacity: 200.0 mL }
        wash_buffer: { volume: 200.0 mL, capacity: 500.0 mL }
        elution_buffer: { volume: 50.0 mL, capacity: 100.0 mL }
        ni_column: { volume: 0.0 mL, capacity: 20.0 mL }
        lysate_tube: { volume: 0.0 mL, capacity: 100.0 mL }
        elution_tube: { volume: 0.0 mL, capacity: 50.0 mL }
        pellet_tube: { volume: 0.0 mL, capacity: 100.0 mL }
    })

    // 诱导表达
    @step(id: "induction", description: "IPTG induction")
    @checkpoint("Before induction")
    let od = measure(culture_flask, property: Absorbance { wavelength: 600 nm })

    if od >= 0.6 {
        add(iptg_stock, to_concentration: 1 mM, to: culture_flask)
        incubate(container: culture_flask, temperature: 18 degC, duration: 16 h, shaker_speed: 200 rpm)
    }

    // 收集细胞
    @step(id: "harvest", description: "Harvest cells")
    @checkpoint("Before centrifugation")
    centrifuge(container: culture_flask, speed: 4000 rpm, duration: 20 min, temperature: 4 degC)

    manual(
        instruction: "Decant supernatant and resuspend pellet in lysis buffer",
        affects: [culture_flask, pellet_tube],
        state_effects: StateDelta {
            pellet_tube: { volume: 50.0 mL }
        }
    )

    // 裂解
    @step(id: "lysis", description: "Cell lysis by sonication")
    incubate(container: pellet_tube, temperature: 4 degC, duration: 30 min)
    manual(instruction: "Sonicate: 30% amplitude, 10s on / 10s off, 5 minutes total")

    // 离心澄清
    centrifuge(container: pellet_tube, speed: 15000 rpm, duration: 30 min, temperature: 4 degC)
    transfer(from: pellet_tube, to: lysate_tube, volume: 45.0 mL)

    // 亲和纯化
    @step(id: "purification", description: "Ni-NTA purification")
    @checkpoint("Begin purification")

    // 平衡柱子
    transfer(from: wash_buffer, to: ni_column, volume: 20.0 mL)

    // 上样
    transfer(from: lysate_tube, to: ni_column, volume: 45.0 mL)

    // 洗涤
    transfer(from: wash_buffer, to: ni_column, volume: 50.0 mL)
    transfer(from: wash_buffer, to: ni_column, volume: 50.0 mL)

    // 洗脱
    @step(id: "elution", description: "Protein elution")
    transfer(from: elution_buffer, to: ni_column, volume: 10.0 mL)
    transfer(from: ni_column, to: elution_tube, volume: 10.0 mL)

    // 存储
    @checkpoint("Purification complete")
    store(container: elution_tube, temperature: -80 degC)
}
```

### 10.4 96孔板细胞培养

```bpl
protocol CellCulture96Well {
    manual(instruction: "Prepare cell suspension, medium, and 96-well plate", state_effects: StateDelta {
        cell_suspension: { volume: 15.0 mL, capacity: 50.0 mL }
        complete_medium: { volume: 100.0 mL, capacity: 200.0 mL }
        culture_plate: { volume: 0.0 uL, capacity: 38400.0 uL }
        compound_plate: { volume: 9600.0 uL, capacity: 20000.0 uL }
    })

    @step(id: "seed", description: "Seed cells")
    @checkpoint("Begin cell seeding")

    // 分配培养基
    distribute(from: complete_medium, to: culture_plate, volume: 100.0 uL)

    // 接种细胞
    distribute(from: cell_suspension, to: culture_plate, volume: 100.0 uL)

    // 混匀
    mix(container: culture_plate, volume: 100.0 uL, repetitions: 3, distribution: "all")

    // 培养过夜让细胞贴壁
    @step(id: "attach", description: "Cell attachment")
    incubate(container: culture_plate, temperature: 37 degC, duration: 24 h)

    // 添加化合物处理
    @step(id: "treatment", description: "Add compounds")
    @checkpoint("Before compound addition")
    stamp(from: compound_plate, to: culture_plate, volume: 10.0 uL)

    // 继续培养
    @step(id: "incubation", description: "Compound incubation")
    incubate(container: culture_plate, temperature: 37 degC, duration: 48 h)

    // 检测
    @step(id: "readout", description: "Measure cell viability")
    @checkpoint("Before measurement")
    measure(culture_plate, property: Absorbance { wavelength: 490 nm })
}
```

### 10.5 带错误处理的自动化转移

```bpl
recovery TipClogRecovery {
    @for_error: TipClog
    drop_tips(to: Waste)
    pick_tips(type: same_as_before, count: same_as_before)
}

recovery LiquidNotFoundRecovery {
    @for_error: LiquidNotFound
    manual(instruction: "Check and refill source container if needed")
}

protocol RobustAutomatedTransfer {
    @error_policy: {
        TipClog: Retry { max: 3, delay: 5 s, with_fresh_tip: true, recovery: TipClogRecovery },
        LiquidNotFound: AlertAndContinue { timeout: 120 s, default_action: Skip },
        CollisionDetected: Stop,
        default: Stop
    }

    @batch_error_policy: CollectAndReport {
        max_failures: 8,
        failure_threshold: 0.1,
        report_at_end: true
    }

    manual(instruction: "Load source and destination plates", state_effects: StateDelta {
        source_plate: { volume: 19200.0 uL, capacity: 38400.0 uL }
        dest_plate: { volume: 0.0 uL, capacity: 38400.0 uL }
        tip_rack: { volume: 0.0 uL, capacity: 10000.0 uL }
    })

    @step(id: "transfer", description: "96-well plate transfer")
    @checkpoint("Begin automated transfer")

    @on_error(match: TipClog, action: Retry { max: 2, recovery: TipClogRecovery })
    @on_error(match: LiquidNotFound, action: Skip { log_reason: true, continue_batch: true })
    stamp(from: source_plate, to: dest_plate, volume: 100.0 uL)

    @checkpoint("Transfer complete")
    seal(container: dest_plate)
}
```

### 10.6 GMP合规性协议示例

```bpl
protocol GMPQualityControl {
    @compliance(GMP)
    @context(GMP)
    @electronic_signatures(Part11)

    @error_policy: { default: Stop }

    manual(instruction: "Verify equipment calibration and prepare reference standards",
           state_effects: StateDelta {
        reference_standard: { volume: 1.0 mL, capacity: 5.0 mL }
        test_samples: { volume: 10.0 mL, capacity: 20.0 mL }
        qc_plate: { volume: 0.0 uL, capacity: 38400.0 uL }
    })

    @step(id: "S1", description: "Equipment verification")
    @step(critical)
    @witness_required
    manual(
        instruction: "Verify calibration status of pipettes and plate reader",
        record: [
            TextField { name: "pipette_calibration_id", required: true },
            TextField { name: "reader_calibration_id", required: true },
            DateField { name: "calibration_date", required: true }
        ]
    )

    @step(id: "S2", description: "Reference standard preparation")
    @step(critical)
    @checkpoint("Reference standards loaded")
    transfer(from: reference_standard, to: qc_plate[A1:A3], volume: 100.0 uL)

    @step(id: "S3", description: "Sample loading")
    @checkpoint("Samples loaded")
    transfer(from: test_samples, to: qc_plate[B1:H12], volume: 100.0 uL)

    @step(id: "S4", description: "Measurement")
    @step(critical)
    @checkpoint("Before measurement")
    let results = measure(qc_plate, property: Absorbance { wavelength: 450 nm })

    @step(id: "S5", description: "Data review and sign-off")
    @step(critical)
    @witness_required
    @electronic_signatures(Part11)
    manual(
        instruction: "Review results and sign off on data integrity",
        record: [
            TextField { name: "reviewer_name", required: true },
            TextField { name: "review_comments", required: false },
            BooleanField { name: "data_acceptable", required: true }
        ]
    )

    @assert(results.reference_cv < 0.05, "Reference standard CV exceeds 5% limit")

    @checkpoint("QC protocol complete")
}
```

---

## 附录A：运算符优先级

| 优先级 | 运算符 | 结合性 |
|--------|--------|--------|
| 1 | `()` | - |
| 2 | `!`, `not` | 右 |
| 3 | `*`, `/`, `mod` | 左 |
| 4 | `+`, `-` | 左 |
| 5 | `..` | - |
| 6 | `<`, `<=`, `>`, `>=` | 左 |
| 7 | `==`, `!=`, `in`, `not in` | 左 |
| 8 | `&&` | 左 |
| 9 | `\|\|` | 左 |

## 附录B：保留关键字

```
protocol, reagent, stock, labware, labware_category, deck_model, target,
resource, type, function, intent, primitive, recovery, invariant, pcr_profile,
module, import, from, as, version,
if, else, for, in, while, return, let,
parallel, sequence,
true, false, null,
Solid, Liquid, Gas,
Research, GLP, GMP, GxP
```

## 附录C：常用单位速查表

| 类别 | 单位 | 换算关系 |
|------|------|----------|
| 体积 | `L`, `mL`, `uL`, `nL` | 1 L = 1000 mL = 10⁶ uL |
| 质量 | `kg`, `g`, `mg`, `ug`, `ng`, `pg` | 1 g = 1000 mg = 10⁶ ug |
| 时间 | `d`, `h`, `min`, `s`, `ms` | 1 h = 60 min = 3600 s |
| 温度 | `degC`, `K` | K = degC + 273.15 |
| 浓度 | `M`, `mM`, `uM`, `nM`, `pM` | 1 M = 1000 mM = 10⁶ uM |
| 长度 | `bp`, `kb`, `Mb` | 1 kb = 1000 bp |

---

*本文档由BPL项目自动生成，版权所有 © 2025*
