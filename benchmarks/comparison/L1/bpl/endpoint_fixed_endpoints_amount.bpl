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
    aliquot(amount: 10 uL)
    aliquot(amount: 20 uL)
}
function aliquot(amount: Volume) {
    transfer(from: StockTube, to: TargetTube, volume: amount)
}
