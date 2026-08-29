/* Odin core:crypto/sha2 — native SHA-256 with Intel/ARM HW paths in the stdlib. */
package sha256_runner

import "core:crypto/hash"
import "core:encoding/hex"
import "core:fmt"
import "core:io"
import "core:os"
import "core:strconv"
import "core:time"

WARMUP_BUDGET_NS :: i64(200_000_000)
WARMUP_MAX_ITERS :: u64(100_000)

fill_buf :: proc(buf: []u8, seed: u64) {
	s := seed if seed != 0 else u64(0xC0FFEE)
	for i in 0 ..< len(buf) {
		s = s * 6364136223846793005 + 1
		buf[i] = u8(s >> 56)
	}
}

digest_into :: proc(data: []u8, out: []u8) {
	hash.hash_bytes_to_buffer(.SHA256, data, out)
}

digest_hex :: proc(data: []u8, allocator := context.allocator) -> string {
	out: [32]u8
	digest_into(data, out[:])
	encoded, _ := hex.encode(out[:], allocator = allocator)
	return string(encoded)
}

read_all_stdin :: proc(allocator := context.allocator) -> ([]u8, bool) {
	stream := os.to_stream(os.stdin)
	buf: [dynamic]u8
	buf.allocator = allocator
	tmp: [65536]u8
	for {
		n, err := io.read(stream, tmp[:])
		if n > 0 {
			append(&buf, ..tmp[:n])
		}
		if err == .EOF || (err != nil && n == 0) {
			break
		}
		if err != nil && err != .EOF {
			return nil, false
		}
	}
	return buf[:], true
}

cmd_hash :: proc() -> int {
	data, ok := read_all_stdin()
	if !ok {
		fmt.eprintf("read stdin failed\n")
		return 1
	}
	defer delete(data)
	hex_str := digest_hex(data)
	defer delete(hex_str)
	fmt.printf("%s\n", hex_str)
	return 0
}

cmd_verify :: proc() -> int {
	stream := os.to_stream(os.stdin)
	for {
		lenbuf: [4]u8
		n, err := io.read_full(stream, lenbuf[:])
		if err == .EOF || n < 4 {
			return 0
		}
		if err != nil {
			fmt.eprintf("verify length read failed\n")
			return 1
		}
		msg_len := (uint(lenbuf[0]) << 24) | (uint(lenbuf[1]) << 16) | (uint(lenbuf[2]) << 8) | uint(lenbuf[3])
		buf := make([]u8, msg_len)
		defer delete(buf)
		if msg_len > 0 {
			_, err = io.read_full(stream, buf)
			if err != nil {
				fmt.eprintf("verify body read failed\n")
				return 1
			}
		}
		hex_str := digest_hex(buf)
		defer delete(hex_str)
		fmt.printf("%s\n", hex_str)
	}
}

cmd_bench :: proc(size: int, iters: u64, seed: u64) -> int {
	cap := size if size > 0 else 1
	buf := make([]u8, cap)
	defer delete(buf)
	slice := buf[:size]
	if size > 0 {
		fill_buf(slice, seed)
	}
	last: [32]u8
	w0 := time.tick_now()
	for _ in 0 ..< WARMUP_MAX_ITERS {
		digest_into(slice, last[:])
		if time.duration_nanoseconds(time.tick_since(w0)) >= WARMUP_BUDGET_NS {
			break
		}
	}
	t0 := time.tick_now()
	for _ in 0 ..< iters {
		digest_into(slice, last[:])
	}
	ns := time.duration_nanoseconds(time.tick_since(t0))
	hex_str := string(hex.encode(last[:]) or_else {})
	defer delete(hex_str)
	fmt.printf(
		"{{\"ns_total\":%v,\"hashes\":%v,\"size\":%v,\"digest\":\"%s\"}}\n",
		ns,
		iters,
		size,
		hex_str,
	)
	return 0
}

main :: proc() {
	if len(os.args) < 2 {
		fmt.eprintf("usage: sha256_runner hash | verify | bench SIZE ITERS [SEED]\n")
		os.exit(2)
	}
	switch os.args[1] {
	case "hash":
		os.exit(cmd_hash())
	case "verify":
		os.exit(cmd_verify())
	case "bench":
		if len(os.args) < 4 {
			fmt.eprintf("usage: sha256_runner bench SIZE ITERS [SEED]\n")
			os.exit(2)
		}
		size, _ := strconv.parse_int(os.args[2])
		iters64, _ := strconv.parse_u64(os.args[3])
		seed: u64 = 1
		if len(os.args) >= 5 {
			seed, _ = strconv.parse_u64(os.args[4])
		}
		os.exit(cmd_bench(size, iters64, seed))
	case:
		fmt.eprintf("usage: sha256_runner hash | verify | bench SIZE ITERS [SEED]\n")
		os.exit(2)
	}
}
