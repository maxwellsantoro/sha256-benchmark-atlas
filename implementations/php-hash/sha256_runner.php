#!/usr/bin/env php
<?php
declare(strict_types=1);

function fill_buf(int $size, int $seed): string {
    $s = gmp_init($seed === 0 ? '12632214' : (string)$seed); // 0xC0FFEE
    $mask = gmp_init('18446744073709551615');
    $mul = gmp_init('6364136223846793005');
    $buf = '';
    for ($i = 0; $i < $size; $i++) {
        $s = gmp_and(gmp_add(gmp_mul($s, $mul, 1), 1), $mask);
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

function cmd_verify(): void {
    while (true) {
        $hdr = fread(STDIN, 4);
        if ($hdr === false || strlen($hdr) < 4) {
            break;
        }
        $arr = unpack('N', $hdr);
        $n = $arr[1];
        $data = $n > 0 ? fread(STDIN, $n) : '';
        if ($data === false || strlen($data) !== $n) {
            fwrite(STDERR, "truncated verify message\n");
            exit(1);
        }
        echo digest_hex($data), "\n";
        fflush(STDOUT);
    }
}

function cmd_bench(int $size, int $iters, int $seed): void {
    $buf = fill_buf($size, $seed);
    $last = digest_hex($buf);
    for ($i = 0; $i < 3; $i++) {
        $last = digest_hex($buf);
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
