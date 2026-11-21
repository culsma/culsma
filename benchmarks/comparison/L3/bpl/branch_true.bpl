protocol Main {
    wait(duration: 1 s)
    if true {
        transfer(from: "plate_1:A1", to: "plate_1:A2", volume: 10 uL)
    } else {
        transfer(from: "plate_1:A1", to: "plate_1:A3", volume: 20 uL)
    }
}
