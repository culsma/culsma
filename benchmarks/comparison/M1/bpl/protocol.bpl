labware TubeA {
 footprint: Custom
 well_volume: 1500 uL
}
labware TubeB {
 footprint: Custom
 well_volume: 1500 uL
}
protocol Test {
 transfer(from: TubeA, to: TubeB, volume: 20 uL)
}
