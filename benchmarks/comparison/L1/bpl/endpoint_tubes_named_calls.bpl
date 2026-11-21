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
    aliquot(source: StockTube, destination: TargetTube, amount: 10 uL)
    aliquot(source: StockTube, destination: TargetTube, amount: 20 uL)
}
function aliquot(source: Labware, destination: Labware, amount: Volume) {
    transfer(from: source, to: destination, volume: amount)
}
