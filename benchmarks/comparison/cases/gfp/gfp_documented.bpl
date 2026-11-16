// GFP clarification: the same stipulated 160-uL lysate / 100-uL buffer task.
// Physical locations (not computed fraction identities):
// sources:A1 = lysate, later pellet suspension; sources:A2 = buffer;
// sources:A3 = collected supernatant; assay:A1/A2/A3 = assay wells.
// Initial deck contents are supplied by gfp_bpl.py via the public simulator API.
protocol GFPClarification {
    centrifuge(container: "sources:A1", speed: 12000 rcf, duration: 10 min, temperature: 22 degC)
    // The operator selects supernatant. This transfer does not itself define
    // selective fractionation or assert that cellular material was retained.
    transfer(from: "sources:A1", to: "sources:A3", volume: 160 uL)
    transfer(from: "sources:A3", to: "assay:A1", volume: 20 uL)
    transfer(from: "sources:A2", to: "sources:A1", volume: 40 uL)
    mix(container: "sources:A1", volume: 32 uL, repetitions: 1)
    transfer(from: "sources:A1", to: "assay:A2", volume: 20 uL)
    transfer(from: "sources:A2", to: "assay:A3", volume: 20 uL)
    measure("assay", property: Fluorescence { excitation: 488 nm, emission: 510 nm })
}
