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
    transfer(from: StockTube, to: TargetTube, volume: 10 uL)
    transfer(from: StockTube, to: TargetTube, volume: 20 uL)
}
