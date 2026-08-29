import org.bouncycastle.jce.provider.BouncyCastleProvider;

import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.EOFException;
import java.io.InputStream;
import java.security.MessageDigest;
import java.security.Security;

public class Sha256Runner {
    static {
        if (Security.getProvider(BouncyCastleProvider.PROVIDER_NAME) == null) {
            Security.addProvider(new BouncyCastleProvider());
        }
    }

    private static final char[] HEX_DIGITS = "0123456789abcdef".toCharArray();

    // String.format("%02x", ...) per byte goes through java.util.Formatter's
    // format-string parser on every call — measured at ~9,100 ns for a 32-byte
    // digest vs ~130 ns for a lookup table (70x). It dominated every small/
    // medium-size bench result regardless of the digest algorithm's own speed.
    static String toHex(byte[] bytes) {
        char[] out = new char[bytes.length * 2];
        for (int i = 0; i < bytes.length; i++) {
            int v = bytes[i] & 0xFF;
            out[i * 2] = HEX_DIGITS[v >>> 4];
            out[i * 2 + 1] = HEX_DIGITS[v & 0x0F];
        }
        return new String(out);
    }

    static byte[] fillBuf(int size, long seed) {
        long s = seed == 0 ? 0xC0FFEEL : seed;
        byte[] buf = new byte[size];
        for (int i = 0; i < size; i++) {
            s = s * 6364136223846793005L + 1L;
            buf[i] = (byte) (s >>> 56);
        }
        return buf;
    }

    static MessageDigest newDigest() throws Exception {
        return MessageDigest.getInstance("SHA-256", BouncyCastleProvider.PROVIDER_NAME);
    }

    // Reuses one MessageDigest via reset() instead of calling getInstance() per
    // hash. getInstance() does a Security-provider registry lookup that costs
    // far more than SHA-256 itself on small inputs; calling it inside a timed
    // loop measures provider resolution, not the digest (see PAIN.md's
    // "process startup must stay outside the timed region").
    static String digestHex(MessageDigest md, byte[] data) {
        md.reset();
        return toHex(md.digest(data));
    }

    static void cmdHash() throws Exception {
        byte[] data = System.in.readAllBytes();
        System.out.println(digestHex(newDigest(), data));
    }

    static void cmdVerify() throws Exception {
        MessageDigest md = newDigest();
        DataInputStream in = new DataInputStream(System.in);
        while (true) {
            int len;
            try {
                len = in.readInt();
            } catch (EOFException e) {
                break;
            }
            byte[] buf = new byte[len];
            in.readFully(buf);
            System.out.println(digestHex(md, buf));
            System.out.flush();
        }
    }

    // Warm up on a time budget instead of a fixed iteration count. A constant 3 leaves
    // tiered/JIT runtimes in the interpreter for much of the timed loop, and is at the
    // same time far too many iterations for a multi-second software hash of a large
    // buffer. Every runner in this atlas uses the same two numbers.
    static final long WARMUP_BUDGET_NS = 200_000_000L; // 200 ms
    static final long WARMUP_MAX_ITERS = 100_000L;

    static void cmdBench(int size, long iters, long seed) throws Exception {
        MessageDigest md = newDigest();
        byte[] buf = fillBuf(size, seed);
        String last = digestHex(md, buf);
        long w0 = System.nanoTime();
        for (long w = 0; w < WARMUP_MAX_ITERS; w++) {
            last = digestHex(md, buf);
            if (System.nanoTime() - w0 >= WARMUP_BUDGET_NS) break;
        }
        long t0 = System.nanoTime();
        for (long i = 0; i < iters; i++) last = digestHex(md, buf);
        long ns = System.nanoTime() - t0;
        System.out.println(
            "{\"ns_total\":" + ns + ",\"hashes\":" + iters + ",\"size\":" + size
                + ",\"digest\":\"" + last + "\"}"
        );
    }

    public static void main(String[] args) throws Exception {
        if (args.length < 1) {
            System.err.println("usage: Sha256Runner hash | verify | bench SIZE ITERS [SEED]");
            System.exit(2);
        }
        if (args[0].equals("hash")) {
            cmdHash();
            return;
        }
        if (args[0].equals("verify")) {
            cmdVerify();
            return;
        }
        if (args[0].equals("bench") && args.length >= 3) {
            int size = Integer.parseInt(args[1]);
            long iters = Long.parseLong(args[2]);
            long seed = args.length >= 4 ? Long.parseLong(args[3]) : 1L;
            cmdBench(size, iters, seed);
            return;
        }
        System.err.println("usage: Sha256Runner hash | verify | bench SIZE ITERS [SEED]");
        System.exit(2);
    }
}
