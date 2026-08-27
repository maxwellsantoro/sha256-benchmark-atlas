const std = @import("std");

fn fillBuf(out: []u8, seed: u64) void {
    var s: u64 = if (seed == 0) 0xC0FFEE else seed;
    for (out) |*b| {
        s = s *% 6364136223846793005 +% 1;
        b.* = @truncate(s >> 56);
    }
}

fn digestHex(data: []const u8, hexbuf: *[64]u8) []const u8 {
    var out: [32]u8 = undefined;
    std.crypto.hash.sha2.Sha256.hash(data, &out, .{});
    return std.fmt.bufPrint(hexbuf, "{s}", .{std.fmt.fmtSliceHexLower(&out)}) catch unreachable;
}

fn readAllStdin(allocator: std.mem.Allocator) ![]u8 {
    var stdin = std.io.getStdIn().reader();
    var list: std.ArrayList(u8) = .empty;
    errdefer list.deinit(allocator);
    var buf: [65536]u8 = undefined;
    while (true) {
        const n = try stdin.read(&buf);
        if (n == 0) break;
        try list.appendSlice(allocator, buf[0..n]);
    }
    return try list.toOwnedSlice(allocator);
}

fn cmdHash(allocator: std.mem.Allocator) !void {
    const data = try readAllStdin(allocator);
    defer allocator.free(data);
    var hexbuf: [64]u8 = undefined;
    const hex = digestHex(data, &hexbuf);
    try std.io.getStdOut().writer().print("{s}\n", .{hex});
}

fn readExact(reader: anytype, buf: []u8) !void {
    var got: usize = 0;
    while (got < buf.len) {
        const n = try reader.read(buf[got..]);
        if (n == 0) return error.EndOfStream;
        got += n;
    }
}

fn cmdVerify(allocator: std.mem.Allocator) !void {
    var stdin = std.io.getStdIn().reader();
    var stdout = std.io.getStdOut().writer();
    var lenbuf: [4]u8 = undefined;
    var hexbuf: [64]u8 = undefined;
    while (true) {
        readExact(stdin, &lenbuf) catch break;
        const len: usize = std.mem.readInt(u32, &lenbuf, .big);
        const owned = try allocator.alloc(u8, len);
        defer allocator.free(owned);
        if (len > 0) try readExact(stdin, owned);
        const hex = digestHex(owned, &hexbuf);
        try stdout.print("{s}\n", .{hex});
    }
}

fn cmdBench(allocator: std.mem.Allocator, size: usize, iters: u64, seed: u64) !void {
    const buf = try allocator.alloc(u8, if (size == 0) 1 else size);
    defer allocator.free(buf);
    const slice = if (size == 0) buf[0..0] else buf[0..size];
    if (size > 0) fillBuf(buf[0..size], seed);
    var hexbuf: [64]u8 = undefined;
    var last = digestHex(slice, &hexbuf);
    var i: u32 = 0;
    while (i < 3) : (i += 1) last = digestHex(slice, &hexbuf);
    const t0 = std.time.nanoTimestamp();
    var j: u64 = 0;
    while (j < iters) : (j += 1) last = digestHex(slice, &hexbuf);
    const ns = std.time.nanoTimestamp() - t0;
    try std.io.getStdOut().writer().print(
        "{{\"ns_total\":{d},\"hashes\":{d},\"size\":{d},\"digest\":\"{s}\"}}\n",
        .{ ns, iters, size, last },
    );
}

pub fn main() !void {
    var gpa = std.heap.GeneralPurposeAllocator(.{}){};
    defer _ = gpa.deinit();
    const allocator = gpa.allocator();
    const args = try std.process.argsAlloc(allocator);
    defer std.process.argsFree(allocator, args);
    if (args.len < 2) {
        std.debug.print("usage: sha256_runner hash | verify | bench SIZE ITERS [SEED]\n", .{});
        return error.InvalidArgument;
    }
    if (std.mem.eql(u8, args[1], "hash")) {
        try cmdHash(allocator);
    } else if (std.mem.eql(u8, args[1], "verify")) {
        try cmdVerify(allocator);
    } else if (std.mem.eql(u8, args[1], "bench") and args.len >= 4) {
        const size: usize = try std.fmt.parseInt(usize, args[2], 10);
        const iters: u64 = try std.fmt.parseInt(u64, args[3], 10);
        const seed: u64 = if (args.len >= 5) try std.fmt.parseInt(u64, args[4], 10) else 1;
        try cmdBench(allocator, size, iters, seed);
    } else {
        std.debug.print("usage: sha256_runner hash | verify | bench SIZE ITERS [SEED]\n", .{});
        return error.InvalidArgument;
    }
}
