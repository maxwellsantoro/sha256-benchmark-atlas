use ring::digest::{digest, SHA256};
use std::io::{self, Read, Write};
use std::time::Instant;

fn fill_buf(size: usize, seed: u64) -> Vec<u8> {
    let mut s = if seed == 0 { 0xC0FFEE } else { seed };
    let mut buf = vec![0u8; size];
    for b in &mut buf {
        s = s.wrapping_mul(6364136223846793005).wrapping_add(1);
        *b = (s >> 56) as u8;
    }
    buf
}

fn digest_hex(data: &[u8]) -> String {
    hex_encode(digest(&SHA256, data).as_ref())
}

fn hex_encode(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

fn cmd_hash() -> io::Result<()> {
    let mut buf = Vec::new();
    io::stdin().read_to_end(&mut buf)?;
    println!("{}", digest_hex(&buf));
    Ok(())
}

fn cmd_verify() -> io::Result<()> {
    let mut stdin = io::stdin().lock();
    let mut stdout = io::stdout().lock();
    loop {
        let mut lenbuf = [0u8; 4];
        match stdin.read_exact(&mut lenbuf) {
            Ok(()) => {}
            Err(e) if e.kind() == io::ErrorKind::UnexpectedEof => break,
            Err(e) => return Err(e),
        }
        let len = u32::from_be_bytes(lenbuf) as usize;
        let mut buf = vec![0u8; len];
        if len > 0 {
            stdin.read_exact(&mut buf)?;
        }
        writeln!(stdout, "{}", digest_hex(&buf))?;
    }
    Ok(())
}

fn cmd_bench(size: usize, iters: u64, seed: u64) {
    let buf = fill_buf(size, seed);
    let mut last = digest(&SHA256, &buf);
    for _ in 0..3 {
        last = digest(&SHA256, &buf);
    }
    let t0 = Instant::now();
    for _ in 0..iters {
        last = digest(&SHA256, &buf);
    }
    let ns = t0.elapsed().as_nanos();
    println!(
        "{{\"ns_total\":{ns},\"hashes\":{iters},\"size\":{size},\"digest\":\"{}\"}}",
        hex_encode(last.as_ref())
    );
}

fn main() {
    let mut args = std::env::args().skip(1);
    match args.next().as_deref() {
        Some("hash") => {
            if let Err(e) = cmd_hash() {
                eprintln!("{e}");
                std::process::exit(1);
            }
        }
        Some("verify") => {
            if let Err(e) = cmd_verify() {
                eprintln!("{e}");
                std::process::exit(1);
            }
        }
        Some("bench") => {
            let size: usize = args.next().and_then(|s| s.parse().ok()).unwrap_or(0);
            let iters: u64 = args.next().and_then(|s| s.parse().ok()).unwrap_or(1);
            let seed: u64 = args.next().and_then(|s| s.parse().ok()).unwrap_or(1);
            cmd_bench(size, iters, seed);
        }
        _ => {
            eprintln!("usage: sha256_runner hash | verify | bench SIZE ITERS [SEED]");
            std::process::exit(2);
        }
    }
}
