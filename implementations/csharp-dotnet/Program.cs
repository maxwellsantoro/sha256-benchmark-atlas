// .NET System.Security.Cryptography.SHA256 — OS-backed (CNG / OpenSSL / CommonCrypto).
using System.Security.Cryptography;
using System.Text.Json;

const long WarmupBudgetNs = 200_000_000;
const long WarmupMaxIters = 100_000;

static byte[] FillBuf(int size, ulong seed)
{
    if (seed == 0) seed = 0xC0FFEE;
    var buf = new byte[size];
    for (int i = 0; i < size; i++)
    {
        seed = seed * 6364136223846793005UL + 1UL;
        buf[i] = (byte)(seed >> 56);
    }
    return buf;
}

static string DigestHex(ReadOnlySpan<byte> data)
{
    Span<byte> hash = stackalloc byte[32];
    SHA256.HashData(data, hash);
    return ToHexLower(hash);
}

static string ToHexLower(ReadOnlySpan<byte> bytes)
{
    // Convert.ToHexStringLower is .NET 9+; atlas CI targets .NET 8.
    return Convert.ToHexString(bytes).ToLowerInvariant();
}

static int CmdHash()
{
    using var ms = new MemoryStream();
    Console.OpenStandardInput().CopyTo(ms);
    Console.WriteLine(DigestHex(ms.ToArray()));
    return 0;
}

static int CmdVerify()
{
    using var stdin = Console.OpenStandardInput();
    var lenbuf = new byte[4];
    while (true)
    {
        int got = 0;
        while (got < 4)
        {
            int n = stdin.Read(lenbuf, got, 4 - got);
            if (n <= 0) return 0;
            got += n;
        }
        int len = (lenbuf[0] << 24) | (lenbuf[1] << 16) | (lenbuf[2] << 8) | lenbuf[3];
        var buf = new byte[len];
        int filled = 0;
        while (filled < len)
        {
            int n = stdin.Read(buf, filled, len - filled);
            if (n <= 0) return 1;
            filled += n;
        }
        Console.WriteLine(DigestHex(buf));
    }
}

static int CmdBench(int size, ulong iters, ulong seed)
{
    var buf = FillBuf(size, seed);
    Span<byte> last = stackalloc byte[32];
    var w0 = DateTime.UtcNow.Ticks;
    for (long w = 0; w < WarmupMaxIters; w++)
    {
        SHA256.HashData(buf, last);
        var elapsed = (DateTime.UtcNow.Ticks - w0) * 100; // ticks → ns (100 ns units)
        if (elapsed >= WarmupBudgetNs) break;
    }
    var sw = System.Diagnostics.Stopwatch.StartNew();
    for (ulong i = 0; i < iters; i++)
        SHA256.HashData(buf, last);
    sw.Stop();
    var ns = (long)(sw.Elapsed.TotalNanoseconds);
    var digest = ToHexLower(last);
    Console.WriteLine(
        JsonSerializer.Serialize(new Dictionary<string, object>
        {
            ["ns_total"] = ns,
            ["hashes"] = iters,
            ["size"] = size,
            ["digest"] = digest,
        })
    );
    return 0;
}

if (args.Length < 1)
{
    Console.Error.WriteLine("usage: sha256_runner hash | verify | bench SIZE ITERS [SEED]");
    return 2;
}

switch (args[0])
{
    case "hash":
        return CmdHash();
    case "verify":
        return CmdVerify();
    case "bench" when args.Length >= 3:
        {
            int size = int.Parse(args[1]);
            ulong iters = ulong.Parse(args[2]);
            ulong seed = args.Length >= 4 ? ulong.Parse(args[3]) : 1UL;
            return CmdBench(size, iters, seed);
        }
    default:
        Console.Error.WriteLine("usage: sha256_runner hash | verify | bench SIZE ITERS [SEED]");
        return 2;
}
