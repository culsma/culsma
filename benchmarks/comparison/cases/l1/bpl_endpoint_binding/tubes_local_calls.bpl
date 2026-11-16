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
    let source: Labware = StockTube
    let destination: Labware = TargetTube
    aliquot(source: source, destination: destination, amount: 10 uL)
    aliquot(source: source, destination: destination, amount: 20 uL)
}
function aliquot(source: Labware, destination: Labware, amount: Volume) {
    transfer(from: source, to: destination, volume: amount)
}
