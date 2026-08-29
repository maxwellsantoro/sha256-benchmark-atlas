#!/usr/bin/env php
<?php
declare(strict_types=1);

function fill_buf(int $size, int $seed): string {
    $s = gmp_init($seed === 0 ? '12632214' : (string)$seed); // 0xC0FFEE
    $mask = gmp_init('18446744073709551615');
    $mul = gmp_init('6364136223846793005');
    $buf = '';
    for ($i = 0; $i < $size; $i++) {
        $s = gmp_and(gmp_add(gmp_mul($s, $mul), 1), $mask);
        $byte = gmp_intval(gmp_div_q($s, gmp_pow(2, 56))) & 0xFF;
        $buf .= chr($byte);
    }
    return $buf;
}

function digest_hex(string $data): string {
    return hash('sha256', $data);
}

function cmd_hash(): void {
    $data = stream_get_contents(STDIN);
    if ($data === false) {
        fwrite(STDERR, "read failed\n");
        exit(1);
    }
    echo digest_hex($data), "\n";
}

// fread() on a pipe is not guaranteed to return the full requested length in
// one call (short reads are normal, not an error) — loop until $n bytes are
// read or the stream hits EOF, like every other runner's read_exact/readFully.
function read_exact(int $n): string|false {
    $out = '';
    while (strlen($out) < $n) {
        $chunk = fread(STDIN, $n - strlen($out));
        if ($chunk === false || $chunk === '') {
            return false; // EOF before $n bytes were read
        }
        $out .= $chunk;
    }
    return $out;
}

function cmd_verify(): void {
    while (true) {
        $hdr = read_exact(4);
        if ($hdr === false) {
            break;
        }
        $arr = unpack('N', $hdr);
        $n = $arr[1];
        $data = $n > 0 ? read_exact($n) : '';
        if ($data === false) {
            fwrite(STDERR, "truncated verify message\n");
            exit(1);
        }
        echo digest_hex($data), "\n";
        fflush(STDOUT);
    }
}

// Warm up on a time budget instead of a fixed iteration count. A constant 3 leaves
// tiered/JIT runtimes in the interpreter for much of the timed loop, and is at the
// same time far too many iterations for a multi-second software hash of a large
// buffer. Every runner in this atlas uses the same two numbers.
const WARMUP_BUDGET_NS = 200000000; // 200 ms
const WARMUP_MAX_ITERS = 100000;

function cmd_bench(int $size, int $iters, int $seed): void {
    $buf = fill_buf($size, $seed);
    $last = digest_hex($buf);
    $w0 = hrtime(true);
    for ($w = 0; $w < WARMUP_MAX_ITERS; $w++) {
        $last = digest_hex($buf);
        if (hrtime(true) - $w0 >= WARMUP_BUDGET_NS) { break; }
    }
    $t0 = hrtime(true);
    for ($i = 0; $i < $iters; $i++) {
        $last = digest_hex($buf);
    }
    $ns = hrtime(true) - $t0;
    echo json_encode([
        'ns_total' => $ns,
        'hashes' => $iters,
        'size' => $size,
        'digest' => $last,
    ]), "\n";
}

if ($argc < 2) {
    fwrite(STDERR, "usage: sha256_runner.php hash | verify | bench SIZE ITERS [SEED]\n");
    exit(2);
}

switch ($argv[1]) {
    case 'hash':
        cmd_hash();
        break;
    case 'verify':
        cmd_verify();
        break;
    case 'bench':
        if ($argc < 4) {
            fwrite(STDERR, "usage: sha256_runner.php bench SIZE ITERS [SEED]\n");
            exit(2);
        }
        $size = (int)$argv[2];
        $iters = (int)$argv[3];
        $seed = $argc >= 5 ? (int)$argv[4] : 1;
        cmd_bench($size, $iters, $seed);
        break;
    default:
        fwrite(STDERR, "usage: sha256_runner.php hash | verify | bench SIZE ITERS [SEED]\n");
        exit(2);
}
