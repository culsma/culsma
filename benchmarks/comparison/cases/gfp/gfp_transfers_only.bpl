// Control: transfer arithmetic only; no separation, mixing, or measurement.
protocol GFPTransfersOnly {
    transfer(from: "sources:A1", to: "sources:A3", volume: 160 uL)
    transfer(from: "sources:A3", to: "assay:A1", volume: 20 uL)
    transfer(from: "sources:A2", to: "sources:A1", volume: 40 uL)
    transfer(from: "sources:A1", to: "assay:A2", volume: 20 uL)
    transfer(from: "sources:A2", to: "assay:A3", volume: 20 uL)
}
