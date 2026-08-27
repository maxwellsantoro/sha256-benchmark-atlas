#!/usr/bin/env ruby
# frozen_string_literal: true

require "openssl"
require "json"

def fill_buf(size, seed)
  s = seed.zero? ? 0xC0FFEE : seed
  buf = +""
  size.times do
    s = (s * 6364136223846793005 + 1) & 0xFFFFFFFFFFFFFFFF
    buf << ((s >> 56) & 0xFF).chr
  end
  buf.force_encoding(Encoding::BINARY)
end

def digest_hex(data)
  OpenSSL::Digest.hexdigest("SHA256", data)
end

def cmd_hash
  data = $stdin.read
  puts digest_hex(data)
end

def cmd_verify
  loop do
    hdr = $stdin.read(4)
    break if hdr.nil? || hdr.bytesize < 4

    n = hdr.unpack1("N")
    data = n.positive? ? $stdin.read(n) : ""
    raise "truncated verify message" if data.bytesize != n

    puts digest_hex(data)
    $stdout.flush
  end
end

def cmd_bench(size, iters, seed)
  buf = fill_buf(size, seed)
  last = digest_hex(buf)
  3.times { last = digest_hex(buf) }
  t0 = Process.clock_gettime(Process::CLOCK_MONOTONIC, :nanosecond)
  iters.times { last = digest_hex(buf) }
  ns = Process.clock_gettime(Process::CLOCK_MONOTONIC, :nanosecond) - t0
  puts({ ns_total: ns, hashes: iters, size: size, digest: last }.to_json)
end

case ARGV[0]
when "hash"
  cmd_hash
when "verify"
  cmd_verify
when "bench"
  size = Integer(ARGV[1])
  iters = Integer(ARGV[2])
  seed = ARGV[3] ? Integer(ARGV[3]) : 1
  cmd_bench(size, iters, seed)
else
  warn "usage: sha256_runner.rb hash | verify | bench SIZE ITERS [SEED]"
  exit 2
end
