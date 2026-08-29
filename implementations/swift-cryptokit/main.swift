import Foundation
import CryptoKit

// Apple CryptoKit SHA-256 (CommonCrypto underneath on Apple platforms).
// Linux campaign runners will mark this unsupported_platform.

let warmupBudgetNs: UInt64 = 200_000_000
let warmupMaxIters: UInt64 = 100_000

func fillBuf(size: Int, seed: UInt64) -> Data {
    var s = seed == 0 ? UInt64(0xC0FFEE) : seed
    var buf = [UInt8](repeating: 0, count: size)
    for i in 0..<size {
        s = s &* 6364136223846793005 &+ 1
        buf[i] = UInt8(truncatingIfNeeded: s >> 56)
    }
    return Data(buf)
}

func digestHex(_ data: Data) -> String {
    let digest = SHA256.hash(data: data)
    return digest.map { String(format: "%02x", $0) }.joined()
}

func readAllStdin() -> Data {
    FileHandle.standardInput.readDataToEndOfFile()
}

func cmdHash() {
    let data = readAllStdin()
    print(digestHex(data))
}

func cmdVerify() {
    let stdin = FileHandle.standardInput
    while true {
        autoreleasepool {
            guard let lenData = try? stdin.read(upToCount: 4), lenData.count == 4 else {
                exit(0)
            }
            let len = Int(lenData[0]) << 24 | Int(lenData[1]) << 16 | Int(lenData[2]) << 8 | Int(lenData[3])
            var buf = Data()
            if len > 0 {
                guard let chunk = try? stdin.read(upToCount: len), chunk.count == len else {
                    fputs("short read\n", stderr)
                    exit(1)
                }
                buf = chunk
            }
            print(digestHex(buf))
            fflush(stdout)
        }
    }
}

func nowNs() -> UInt64 {
    return UInt64(DispatchTime.now().uptimeNanoseconds)
}

func cmdBench(size: Int, iters: UInt64, seed: UInt64) {
    let buf = fillBuf(size: size, seed: seed)
    var last = ""
    let w0 = nowNs()
    for _ in 0..<warmupMaxIters {
        last = digestHex(buf)
        if nowNs() &- w0 >= warmupBudgetNs { break }
    }
    let t0 = nowNs()
    for _ in 0..<iters {
        last = digestHex(buf)
    }
    let ns = nowNs() &- t0
    print("{\"ns_total\":\(ns),\"hashes\":\(iters),\"size\":\(size),\"digest\":\"\(last)\"}")
}

let args = CommandLine.arguments
guard args.count >= 2 else {
    fputs("usage: sha256_runner hash | verify | bench SIZE ITERS [SEED]\n", stderr)
    exit(2)
}

switch args[1] {
case "hash":
    cmdHash()
case "verify":
    cmdVerify()
case "bench" where args.count >= 4:
    let size = Int(args[2])!
    let iters = UInt64(args[3])!
    let seed = args.count >= 5 ? UInt64(args[4])! : 1
    cmdBench(size: size, iters: iters, seed: seed)
default:
    fputs("usage: sha256_runner hash | verify | bench SIZE ITERS [SEED]\n", stderr)
    exit(2)
}
