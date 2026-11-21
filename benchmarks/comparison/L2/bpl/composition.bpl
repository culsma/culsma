labware StockTube {
    footprint: Custom
    well_count: 1
    well_volume: 1.5 mL
    category: Tube
}
labware TargetTube {
    footprint: Custom
    well_count: 1
    well_volume: 1.5 mL
    category: Tube
}
protocol Main {
    let prepared: Labware = prepare()
    take_aliquot(sample: prepared, destination: TargetTube)
}
function prepare() -> Labware {
    return StockTube
}
function take_aliquot(sample: Labware, destination: Labware) {
    transfer(from: sample, to: destination, volume: 10 uL)
}
