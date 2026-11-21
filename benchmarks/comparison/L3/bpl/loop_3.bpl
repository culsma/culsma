protocol Main {
    wait(duration: 1 s)
    for i in [1, 2, 3] {
        transfer(from: "plate_1:A1", to: "plate_1:A2", volume: 10 uL)
    }
}
