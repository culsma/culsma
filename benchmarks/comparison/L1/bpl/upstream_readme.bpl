reagent Tryptone  { physical_form: Solid, cas: "91079-40-2" }
reagent NaCl      { physical_form: Solid, MW: 58.44 g/mol   }
reagent ROWater   { physical_form: Liquid                    }

stock LB_Base {
    reagent: Tryptone
    concentration: 10 g/L
    solvent: ROWater
}

labware Beaker1L      { footprint: Custom, well_volume: 1200 mL }
labware GlassBottle1L { footprint: Custom, well_volume: 1000 mL }

@target(human)
@expected_time(2 h)
protocol PrepareLBMedia(final_volume: Volume = 1000 mL) {
    @step(1, "Add RO water to beaker")
    add_reagent(ROWater, volume: 800 mL, to: Beaker1L)

    @step(2, "Add Tryptone")
    add_reagent(Tryptone, mass: 10 g, to: Beaker1L)

    @step(3, "Add NaCl")
    add_reagent(NaCl, mass: 10 g, to: Beaker1L)

    @step(4, "Adjust volume")
    add_reagent(ROWater, volume: 200 mL, to: Beaker1L)

    @step(5, "Transfer to bottle")
    transfer(from: Beaker1L, volume: final_volume, to: GlassBottle1L)

    @step(6, "Autoclave")
    incubate(target: GlassBottle1L, temperature: 121 degC, time: 20 min)
}
