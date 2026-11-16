protocol Main {
 aliquot(source: "plate_1:A1", destination: "plate_1:A2", amount: 10 uL)
 aliquot(source: "plate_1:A1", destination: "plate_1:A3", amount: 20 uL)
}
protocol aliquot(source, destination, amount: Volume) {
 transfer(from: source, to: destination, volume: amount)
}
