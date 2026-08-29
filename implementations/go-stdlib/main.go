package main

import (
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"strconv"
	"time"
)

func fillBuf(size int, seed uint64) []byte {
	s := seed
	if s == 0 {
		s = 0xC0FFEE
	}
	buf := make([]byte, size)
	for i := range buf {
		s = s*6364136223846793005 + 1
		buf[i] = byte(s >> 56)
	}
	return buf
}

func cmdHash() error {
	data, err := io.ReadAll(os.Stdin)
	if err != nil {
		return err
	}
	sum := sha256.Sum256(data)
	fmt.Println(hex.EncodeToString(sum[:]))
	return nil
}

func cmdVerify() error {
	for {
		var lenbuf [4]byte
		_, err := io.ReadFull(os.Stdin, lenbuf[:])
		if err == io.EOF || err == io.ErrUnexpectedEOF {
			return nil
		}
		if err != nil {
			return err
		}
		n := binary.BigEndian.Uint32(lenbuf[:])
		buf := make([]byte, n)
		if n > 0 {
			if _, err := io.ReadFull(os.Stdin, buf); err != nil {
				return err
			}
		}
		sum := sha256.Sum256(buf)
		fmt.Println(hex.EncodeToString(sum[:]))
	}
}

// Warm up on a time budget instead of a fixed iteration count. A constant 3 leaves
// tiered/JIT runtimes in the interpreter for much of the timed loop, and is at the
// same time far too many iterations for a multi-second software hash of a large
// buffer. Every runner in this atlas uses the same two numbers.
const (
	warmupBudget    = 200 * time.Millisecond
	warmupMaxIters  = 100_000
)

func cmdBench(size int, iters uint64, seed uint64) {
	buf := fillBuf(size, seed)
	var last [32]byte
	w0 := time.Now()
	for w := uint64(0); w < warmupMaxIters; w++ {
		last = sha256.Sum256(buf)
		if time.Since(w0) >= warmupBudget {
			break
		}
	}
	t0 := time.Now()
	for i := uint64(0); i < iters; i++ {
		last = sha256.Sum256(buf)
	}
	ns := time.Since(t0).Nanoseconds()
	out := map[string]any{
		"ns_total": ns,
		"hashes":   iters,
		"size":     size,
		"digest":   hex.EncodeToString(last[:]),
	}
	enc := json.NewEncoder(os.Stdout)
	_ = enc.Encode(out)
}

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: sha256_runner hash | verify | bench SIZE ITERS [SEED]")
		os.Exit(2)
	}
	switch os.Args[1] {
	case "hash":
		if err := cmdHash(); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
	case "verify":
		if err := cmdVerify(); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
	case "bench":
		if len(os.Args) < 4 {
			fmt.Fprintln(os.Stderr, "usage: sha256_runner bench SIZE ITERS [SEED]")
			os.Exit(2)
		}
		size, _ := strconv.Atoi(os.Args[2])
		iters, _ := strconv.ParseUint(os.Args[3], 10, 64)
		seed := uint64(1)
		if len(os.Args) >= 5 {
			seed, _ = strconv.ParseUint(os.Args[4], 10, 64)
		}
		cmdBench(size, iters, seed)
	default:
		fmt.Fprintln(os.Stderr, "usage: sha256_runner hash | verify | bench SIZE ITERS [SEED]")
		os.Exit(2)
	}
}
