use std::collections::HashMap;
use std::env;
use std::fs::{File, OpenOptions};
use std::io::{self, BufRead, BufReader, Write};
use std::thread;
use std::time::Duration;

const TRUST_SCALE: f64 = 1000.0;

#[derive(Debug)]
struct Config {
    input: String,
    output: String,
    metrics_out: String,
    blacklist_out: String,
    metric: String,
    alpha: f64,
    beta_a: f64,
    beta_b: f64,
    ewma_min: f64,
    bayes_min: f64,
    beta_min: f64,
    miss_threshold: u64,
    forwarders_only: bool,
    fwd_drop_threshold: f64,
    follow: bool,
    poll_ms: u64,
    from_start: bool,
    serial_socket: Option<String>,
}

#[derive(Debug, Default)]
struct TrustState {
    seen: bool,
    last_seq: u32,
    ewma: f64,
    succ: u64,
    fail: u64,
    last_udp_to_root: u64,
    last_dropped: u64,
}

fn usage() {
    eprintln!("Usage: trust_engine [--input <log>] [--output <trust_out>] [--metrics-out <metrics_csv>] ");
    eprintln!("                  [--metric ewma|bayes|beta] [--alpha <0..1>] [--beta-a <f>] [--beta-b <f>] ");
    eprintln!("                  [--ewma-min <n>] [--bayes-min <0..1>] [--beta-min <0..1>] [--miss-threshold <n>]");
    eprintln!("                  [--forwarders-only] [--fwd-drop-threshold <0..1>]");
    eprintln!("                  [--follow] [--poll-ms <ms>] [--from-start] [--serial-socket <host:port>]");
}

fn parse_args() -> Config {
    let mut cfg = Config {
        input: "logs/COOJA.testlog".to_string(),
        output: "logs/trust_updates.txt".to_string(),
        metrics_out: "logs/trust_metrics.csv".to_string(),
        blacklist_out: "logs/blacklist.csv".to_string(),
        metric: "ewma".to_string(),
        alpha: 0.2,
        beta_a: 1.0,
        beta_b: 1.0,
        ewma_min: 0.7,
        bayes_min: 0.7,
        beta_min: 0.7,
        miss_threshold: 5,
        forwarders_only: false,
        fwd_drop_threshold: 0.2,
        follow: false,
        poll_ms: 200,
        from_start: false,
        serial_socket: None,
    };

    let mut args = env::args().skip(1);
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--input" => {
                if let Some(v) = args.next() { cfg.input = v; }
            }
            "--output" => {
                if let Some(v) = args.next() { cfg.output = v; }
            }
            "--metrics-out" => {
                if let Some(v) = args.next() { cfg.metrics_out = v; }
            }
            "--blacklist-out" => {
                if let Some(v) = args.next() { cfg.blacklist_out = v; }
            }
            "--metric" => {
                if let Some(v) = args.next() { cfg.metric = v; }
            }
            "--alpha" => {
                if let Some(v) = args.next() { cfg.alpha = v.parse().unwrap_or(cfg.alpha); }
            }
            "--beta-a" => {
                if let Some(v) = args.next() { cfg.beta_a = v.parse().unwrap_or(cfg.beta_a); }
            }
            "--beta-b" => {
                if let Some(v) = args.next() { cfg.beta_b = v.parse().unwrap_or(cfg.beta_b); }
            }
            "--ewma-min" => {
                if let Some(v) = args.next() { cfg.ewma_min = v.parse().unwrap_or(cfg.ewma_min); }
            }
            "--bayes-min" => {
                if let Some(v) = args.next() { cfg.bayes_min = v.parse().unwrap_or(cfg.bayes_min); }
            }
            "--beta-min" => {
                if let Some(v) = args.next() { cfg.beta_min = v.parse().unwrap_or(cfg.beta_min); }
            }
            "--miss-threshold" => {
                if let Some(v) = args.next() { cfg.miss_threshold = v.parse().unwrap_or(cfg.miss_threshold); }
            }
            "--forwarders-only" => cfg.forwarders_only = true,
            "--fwd-drop-threshold" => {
                if let Some(v) = args.next() { cfg.fwd_drop_threshold = v.parse().unwrap_or(cfg.fwd_drop_threshold); }
            }
            "--follow" => cfg.follow = true,
            "--poll-ms" => {
                if let Some(v) = args.next() { cfg.poll_ms = v.parse().unwrap_or(cfg.poll_ms); }
            }
            "--from-start" => cfg.from_start = true,
            "--serial-socket" => {
                if let Some(v) = args.next() { cfg.serial_socket = Some(v); }
            }
            "-h" | "--help" => {
                usage();
                std::process::exit(0);
            }
            _ => {}
        }
    }

    cfg
}

fn parse_node_id(ip: &str) -> Option<u16> {
    let last = ip.split(':').filter(|s| !s.is_empty()).last()?;
    u16::from_str_radix(last, 16).ok().or_else(|| last.parse::<u16>().ok())
}

fn process_reader<R: BufRead>(
    mut reader: R,
    cfg: &Config,
    out: &mut File,
    metrics: &mut File,
    blacklist: &mut HashMap<u16, bool>,
    blacklist_out: &mut File,
) -> io::Result<()> {
    let mut states: HashMap<u16, TrustState> = HashMap::new();
    let mut forwarders: HashMap<u16, bool> = HashMap::new();
    loop {
        let mut line = String::new();
        let n = reader.read_line(&mut line)?;
        if n == 0 {
            if cfg.follow && cfg.serial_socket.is_none() {
                thread::sleep(Duration::from_millis(cfg.poll_ms));
                continue;
            } else {
                break;
            }
        }
        if line.starts_with("CSV,FWD,") {
            let parts: Vec<&str> = line.trim().split(',').collect();
            if parts.len() < 6 {
                continue;
            }
            let node_id: u16 = match parts[2].parse() {
                Ok(v) => v,
                Err(_) => continue,
            };
            let udp_to_root: f64 = match parts[4].parse::<u64>() {
                Ok(v) => v as f64,
                Err(_) => continue,
            };
            let dropped: f64 = match parts[5].parse::<u64>() {
                Ok(v) => v as f64,
                Err(_) => continue,
            };
            forwarders.insert(node_id, true);
            let st = states.entry(node_id).or_default();
            let udp_total = udp_to_root as u64;
            let dropped_total = dropped as u64;
            let delta_udp = udp_total.saturating_sub(st.last_udp_to_root);
            let delta_dropped = dropped_total.saturating_sub(st.last_dropped);

            st.last_udp_to_root = udp_total;
            st.last_dropped = dropped_total;

            if delta_udp == 0 {
                continue;
            }

            let delta_success = delta_udp.saturating_sub(delta_dropped);
            let obs = (delta_success as f64) / (delta_udp as f64);

            if !st.seen {
                st.ewma = obs;
                st.seen = true;
            } else {
                st.ewma = cfg.alpha * obs + (1.0 - cfg.alpha) * st.ewma;
            }

            st.succ += delta_success;
            st.fail += delta_dropped;

            let bayes = (1.0 + st.succ as f64) / (2.0 + st.succ as f64 + st.fail as f64);
            let beta = (cfg.beta_a + st.succ as f64) / (cfg.beta_a + cfg.beta_b + st.succ as f64 + st.fail as f64);

            let mut is_blacklisted = *blacklist.get(&node_id).unwrap_or(&false);
            if !is_blacklisted {
                if obs <= (1.0 - cfg.fwd_drop_threshold)
                    || st.ewma < cfg.ewma_min
                    || bayes < cfg.bayes_min
                    || beta < cfg.beta_min
                {
                    is_blacklisted = true;
                    blacklist.insert(node_id, true);
                    let _ = writeln!(
                        blacklist_out,
                        "{},{},{},{:.4},{:.4},{:.4}",
                        node_id,
                        st.succ,
                        st.fail,
                        st.ewma,
                        bayes,
                        beta
                    );
                    let _ = blacklist_out.flush();
                }
            }

            let trust_val = if is_blacklisted {
                0
            } else {
                match cfg.metric.as_str() {
                    "bayes" => (bayes * TRUST_SCALE).round() as u16,
                    "beta" => (beta * TRUST_SCALE).round() as u16,
                    _ => (st.ewma * TRUST_SCALE).round() as u16,
                }
            };

            let _ = writeln!(out, "TRUST,{},{}", node_id, trust_val);
            let _ = out.flush();

            let _ = writeln!(
                metrics,
                "{},{},{},{:.4},{:.4},{:.4}",
                node_id,
                delta_success,
                delta_dropped,
                st.ewma,
                bayes,
                beta
            );
            let _ = metrics.flush();

            continue;
        }
        if !line.starts_with("CSV,RX,") {
            continue;
        }
        let parts: Vec<&str> = line.trim().split(',').collect();
        if parts.len() < 6 {
            continue;
        }
        let node_id = match parse_node_id(parts[2]) {
            Some(v) => v,
            None => continue,
        };
        if cfg.forwarders_only && !forwarders.contains_key(&node_id) {
            continue;
        }
    }
    Ok(())
}

fn main() -> io::Result<()> {
    let cfg = parse_args();

    let mut out = OpenOptions::new()
        .create(true)
        .write(true)
        .truncate(true)
        .open(&cfg.output)?;

    let mut metrics = OpenOptions::new()
        .create(true)
        .write(true)
        .truncate(true)
        .open(&cfg.metrics_out)?;

    writeln!(metrics, "node_id,success,failed,ewma,bayes,beta")?;

    let mut blacklist_out = OpenOptions::new()
        .create(true)
        .write(true)
        .truncate(true)
        .open(&cfg.blacklist_out)?;
    writeln!(blacklist_out, "node_id,success,failed,ewma,bayes,beta")?;

    if let Some(sock) = &cfg.serial_socket {
        let mut parts = sock.split(':');
        let host = parts.next().unwrap_or("127.0.0.1");
        let port = parts.next().unwrap_or("60001");
        let addr = format!("{}:{}", host, port);
        let stream = std::net::TcpStream::connect(addr)?;
        stream.set_nodelay(true).ok();
        let reader = BufReader::new(stream);
        let mut blacklist: HashMap<u16, bool> = HashMap::new();
        process_reader(reader, &cfg, &mut out, &mut metrics, &mut blacklist, &mut blacklist_out)?;
    } else {
        let file = File::open(&cfg.input)?;
        let mut reader = BufReader::new(file);
        if cfg.follow && !cfg.from_start {
            let mut buf = String::new();
            while reader.read_line(&mut buf)? > 0 {
                buf.clear();
            }
        }
        let mut blacklist: HashMap<u16, bool> = HashMap::new();
        process_reader(reader, &cfg, &mut out, &mut metrics, &mut blacklist, &mut blacklist_out)?;
    }

    Ok(())
}
