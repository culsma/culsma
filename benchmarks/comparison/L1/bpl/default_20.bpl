protocol Aliquot(amount: Volume = 20 uL) {
    transfer(from: "plate_1:A1", to: "plate_1:A2", volume: amount)
}
