import java.io.DataInputStream;
import java.io.EOFException;
import java.io.InputStream;
import java.security.MessageDigest;

public class Sha256Runner {
    static String toHex(byte[] bytes) {
        StringBuilder sb = new StringBuilder(bytes.length * 2);
        for (byte b : bytes) {
            sb.append(String.format("%02x", b & 0xff));
        }
        return sb.toString();
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

    static String digestHex(byte[] data) throws Exception {
        MessageDigest md = MessageDigest.getInstance("SHA-256");
        return toHex(md.digest(data));
    }

    static void cmdHash() throws Exception {
        byte[] data = System.in.readAllBytes();
        System.out.println(digestHex(data));
    }

    static void cmdVerify() throws Exception {
        DataInputStream in = new DataInputStream(System.in);
        try {
            while (true) {
                int len;
                try {
                    len = in.readInt();
                } catch (EOFException e) {
                    break;
                }
                byte[] buf = new byte[len];
                in.readFully(buf);
                System.out.println(digestHex(buf));
                System.out.flush();
            }
        } finally {
            // leave System.in open
        }
    }

    static void cmdBench(int size, long iters, long seed) throws Exception {
        byte[] buf = fillBuf(size, seed);
        String last = digestHex(buf);
        for (int i = 0; i < 3; i++) last = digestHex(buf);
        long t0 = System.nanoTime();
        for (long i = 0; i < iters; i++) last = digestHex(buf);
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
