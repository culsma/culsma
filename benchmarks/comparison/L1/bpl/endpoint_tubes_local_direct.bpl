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
    transfer(from: source, to: destination, volume: 10 uL)
    transfer(from: source, to: destination, volume: 20 uL)
}
