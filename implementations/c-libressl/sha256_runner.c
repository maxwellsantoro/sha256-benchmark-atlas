/* c-libressl: atlas SHA-256 runner */
/* Linked against LibreSSL's libcrypto (OpenSSL-compatible EVP API). */
#include <openssl/evp.h>
static int do_hash(const unsigned char *msg, size_t len, unsigned char out[32]) {
    EVP_MD_CTX *ctx = EVP_MD_CTX_new();
    unsigned int outlen = 0;
    if (!ctx) return 1;
    if (EVP_DigestInit_ex(ctx, EVP_sha256(), NULL) != 1 ||
        EVP_DigestUpdate(ctx, msg, len) != 1 ||
        EVP_DigestFinal_ex(ctx, out, &outlen) != 1) {
        EVP_MD_CTX_free(ctx);
        return 1;
    }
    EVP_MD_CTX_free(ctx);
    return outlen == 32 ? 0 : 1;
}

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define WARMUP_BUDGET_NS 200000000ULL
#define WARMUP_MAX_ITERS 100000ULL

static int hex_digest(const unsigned char *d, unsigned int n) {
    for (unsigned int i = 0; i < n; i++)
        printf("%02x", d[i]);
    printf("\n");
    return 0;
}

static uint64_t now_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}

static void fill_buf(unsigned char *buf, size_t n, uint64_t seed) {
    uint64_t s = seed ? seed : 0xC0FFEEULL;
    for (size_t i = 0; i < n; i++) {
        s = s * 6364136223846793005ull + 1ull;
        buf[i] = (unsigned char)(s >> 56);
    }
}

static int read_full(unsigned char *buf, size_t n) {
    size_t got = 0;
    while (got < n) {
        size_t r = fread(buf + got, 1, n - got, stdin);
        if (r == 0) return 1;
        got += r;
    }
    return 0;
}

static int cmd_hash(void) {
    unsigned char *buf = NULL;
    size_t cap = 0, len = 0;
    unsigned char digest[32];
    for (;;) {
        if (len + 65536 > cap) {
            cap = cap ? cap * 2 : 65536;
            unsigned char *nbuf = realloc(buf, cap);
            if (!nbuf) { free(buf); return 1; }
            buf = nbuf;
        }
        size_t n = fread(buf + len, 1, cap - len, stdin);
        len += n;
        if (n == 0) break;
    }
    if (do_hash(buf, len, digest)) { free(buf); return 1; }
    free(buf);
    return hex_digest(digest, 32);
}

static int cmd_verify(void) {
    unsigned char lenbuf[4];
    unsigned char digest[32];
    while (fread(lenbuf, 1, 4, stdin) == 4) {
        size_t len = ((size_t)lenbuf[0] << 24) | ((size_t)lenbuf[1] << 16) |
                     ((size_t)lenbuf[2] << 8) | (size_t)lenbuf[3];
        unsigned char *buf = NULL;
        if (len) {
            buf = malloc(len);
            if (!buf || read_full(buf, len)) { free(buf); return 1; }
        }
        if (do_hash(buf, len, digest)) { free(buf); return 1; }
        free(buf);
        if (hex_digest(digest, 32)) return 1;
        fflush(stdout);
    }
    return 0;
}

static int cmd_bench(size_t size, uint64_t iters, uint64_t seed) {
    unsigned char *buf = calloc(1, size ? size : 1);
    unsigned char digest[32];
    if (!buf && size) return 1;
    fill_buf(buf, size, seed);
    uint64_t w0 = now_ns();
    for (uint64_t w = 0; w < WARMUP_MAX_ITERS; w++) {
        if (do_hash(buf, size, digest)) { free(buf); return 1; }
        if (now_ns() - w0 >= WARMUP_BUDGET_NS) break;
    }
    uint64_t t0 = now_ns();
    for (uint64_t i = 0; i < iters; i++)
        if (do_hash(buf, size, digest)) { free(buf); return 1; }
    uint64_t t1 = now_ns();
    printf("{\"ns_total\":%llu,\"hashes\":%llu,\"size\":%zu,\"digest\":\"",
           (unsigned long long)(t1 - t0),
           (unsigned long long)iters,
           size);
    for (int i = 0; i < 32; i++) printf("%02x", digest[i]);
    printf("\"}\n");
    free(buf);
    return 0;
}

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "usage: %s hash | verify | bench SIZE ITERS [SEED]\n", argv[0]);
        return 2;
    }
    if (strcmp(argv[1], "hash") == 0)
        return cmd_hash();
    if (strcmp(argv[1], "verify") == 0)
        return cmd_verify();
    if (strcmp(argv[1], "bench") == 0 && argc >= 4) {
        size_t size = (size_t)strtoull(argv[2], NULL, 10);
        uint64_t iters = strtoull(argv[3], NULL, 10);
        uint64_t seed = argc >= 5 ? strtoull(argv[4], NULL, 10) : 1;
        return cmd_bench(size, iters, seed);
    }
    fprintf(stderr, "usage: %s hash | verify | bench SIZE ITERS [SEED]\n", argv[0]);
    return 2;
}
