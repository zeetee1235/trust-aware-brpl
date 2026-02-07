use std::collections::{HashMap, HashSet};
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
    exposure_out: String,
    parent_out: String,
    stats_out: String,
    final_out: String,
    stats_interval: u64,
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
    attacker_id: u16,
}

#[derive(Debug, Default)]
struct TrustState {
    seen: bool,
    ewma: f64,
    succ: u64,
    fail: u64,
    last_udp_to_root: u64,
    last_dropped: u64,
}

#[derive(Debug, Default)]
struct ParentState {
    samples: u64,
    changes: u64,
    last_parent: Option<String>,
}

fn usage() {
    eprintln!("Usage: trust_engine [--input <log>] [--output <trust_out>] [--metrics-out <metrics_csv>] ");
    eprintln!("                  [--metric ewma|bayes|beta] [--alpha <0..1>] [--beta-a <f>] [--beta-b <f>] ");
    eprintln!("                  (alpha is EWMA lambda: weight of previous trust value)");
    eprintln!("                  [--ewma-min <n>] [--bayes-min <0..1>] [--beta-min <0..1>] [--miss-threshold <n>]");
    eprintln!("                  [--forwarders-only] [--fwd-drop-threshold <0..1>]");
    eprintln!("                  [--follow] [--poll-ms <ms>] [--from-start] [--serial-socket <host:port>]");
    eprintln!("                  [--attacker-id <id>] [--exposure-out <csv>] [--parent-out <csv>] [--stats-out <csv>] [--stats-interval <n>]");
}

fn parse_args() -> Config {
    let mut cfg = Config {
        input: "logs/COOJA.testlog".to_string(),
        output: "logs/trust_updates.txt".to_string(),
        metrics_out: "logs/trust_metrics.csv".to_string(),
        blacklist_out: "logs/blacklist.csv".to_string(),
        exposure_out: "".to_string(),
        parent_out: "".to_string(),
        stats_out: "".to_string(),
        final_out: "".to_string(),
        stats_interval: 200,
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
        attacker_id: 2,
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
            "--exposure-out" => {
                if let Some(v) = args.next() { cfg.exposure_out = v; }
            }
            "--parent-out" => {
                if let Some(v) = args.next() { cfg.parent_out = v; }
            }
            "--stats-out" => {
                if let Some(v) = args.next() { cfg.stats_out = v; }
            }
            "--final-out" => {
                if let Some(v) = args.next() { cfg.final_out = v; }
            }
            "--stats-interval" => {
                if let Some(v) = args.next() { cfg.stats_interval = v.parse().unwrap_or(cfg.stats_interval); }
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
            "--attacker-id" => {
                if let Some(v) = args.next() { cfg.attacker_id = v.parse().unwrap_or(cfg.attacker_id); }
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
    exposure_out: &mut Option<File>,
    parent_out: &mut Option<File>,
    stats_out: &mut Option<File>,
    final_out: &mut Option<File>,
) -> io::Result<()> {
    let mut states: HashMap<u16, TrustState> = HashMap::new();
    let mut forwarders: HashMap<u16, bool> = HashMap::new();
    let mut parent_states: HashMap<u16, ParentState> = HashMap::new();
    let mut total_parent_samples: u64 = 0;
    let mut total_parent_attacker: u64 = 0;
    let mut e1_den: u64 = 0;
    let mut e1_num: u64 = 0;
    let mut delivered_to_root: HashSet<u64> = HashSet::new();
    let mut passed_attacker: HashSet<u64> = HashSet::new();
    let mut total_tx: u64 = 0;
    let mut tx_seen: HashMap<u64, bool> = HashMap::new();
    let mut line_idx: u64 = 0;
    let mut attacker_udp_total: u64 = 0;
    let mut attacker_udp_dropped: u64 = 0;
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
        line_idx += 1;
        let trimmed = line.trim();
        if trimmed.starts_with("SIMULATION_FINISHED") || trimmed.starts_with("TEST OK") {
            break;
        }

        if trimmed.starts_with("CSV,TX,") {
            let parts: Vec<&str> = trimmed.split(',').collect();
            if parts.len() >= 4 {
                if let (Ok(node_id), Ok(seq)) = (parts[2].parse::<u64>(), parts[3].parse::<u64>()) {
                    let key = (node_id << 32) | (seq & 0xffffffff);
                    if !tx_seen.contains_key(&key) {
                        tx_seen.insert(key, true);
                        total_tx += 1;
                    }
                }
            }
            continue;
        }
        if trimmed.starts_with("CSV,RX,") {
            let parts: Vec<&str> = trimmed.split(',').collect();
            if parts.len() >= 6 && parts[2] == "node=1" {
                if let Some(src_id) = parse_node_id(parts[3]) {
                    if let Ok(seq) = parts[4].parse::<u64>() {
                        let key = ((src_id as u64) << 32) | (seq & 0xffffffff);
                        if delivered_to_root.insert(key) {
                            e1_den += 1;
                            if passed_attacker.contains(&key) {
                                e1_num += 1;
                            }
                        }
                    }
                }
            }
            continue;
        }
        if trimmed.starts_with("CSV,FWD_PKT,") {
            let parts: Vec<&str> = trimmed.split(',').collect();
            if parts.len() >= 5 {
                let node_id: u16 = match parts[2].parse() {
                    Ok(v) => v,
                    Err(_) => continue,
                };
                if node_id == cfg.attacker_id {
                    if let (Ok(src_id), Ok(seq)) = (parts[3].parse::<u64>(), parts[4].parse::<u64>()) {
                        let key = (src_id << 32) | (seq & 0xffffffff);
                        if passed_attacker.insert(key) {
                            if delivered_to_root.contains(&key) {
                                e1_num += 1;
                            }
                        }
                    }
                }
            }
            continue;
        }
        if trimmed.starts_with("CSV,FWD,") {
            let parts: Vec<&str> = trimmed.split(',').collect();
            if parts.len() < 5 {
                continue;
            }
            let node_id: u16 = match parts[2].parse() {
                Ok(v) => v,
                Err(_) => continue,
            };
            let (udp_to_root, dropped) = if parts.len() >= 6 {
                let udp = match parts[4].parse::<u64>() {
                    Ok(v) => v as f64,
                    Err(_) => continue,
                };
                let dr = match parts[5].parse::<u64>() {
                    Ok(v) => v as f64,
                    Err(_) => continue,
                };
                (udp, dr)
            } else {
                let udp = match parts[3].parse::<u64>() {
                    Ok(v) => v as f64,
                    Err(_) => continue,
                };
                let dr = match parts[4].parse::<u64>() {
                    Ok(v) => v as f64,
                    Err(_) => continue,
                };
                (udp, dr)
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

            st.succ += delta_success;
            st.fail += delta_dropped;

            let beta_est = (cfg.beta_a + st.succ as f64)
                / (cfg.beta_a + cfg.beta_b + st.succ as f64 + st.fail as f64);
            let bayes = (1.0 + st.succ as f64) / (2.0 + st.succ as f64 + st.fail as f64);
            let beta = beta_est;

            if !st.seen {
                st.ewma = beta_est;
                st.seen = true;
            } else {
                // EWMA with lambda = cfg.alpha (weight of previous value)
                st.ewma = cfg.alpha * st.ewma + (1.0 - cfg.alpha) * beta_est;
            }

            let mut is_blacklisted = *blacklist.get(&node_id).unwrap_or(&false);
            let mut blacklisted_now = false;
            if !is_blacklisted {
                if beta_est <= (1.0 - cfg.fwd_drop_threshold)
                    || st.ewma < cfg.ewma_min
                    || bayes < cfg.bayes_min
                    || beta < cfg.beta_min
                {
                    is_blacklisted = true;
                    blacklisted_now = true;
                    blacklist.insert(node_id, true);
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
            let trust_value = (trust_val as f64) / TRUST_SCALE;

            if blacklisted_now {
                let _ = writeln!(
                    blacklist_out,
                    "{},{},{},{:.4},{:.4},{:.4},{:.4},{}",
                    node_id,
                    st.succ,
                    st.fail,
                    st.ewma,
                    bayes,
                    beta,
                    trust_value,
                    trust_val
                );
                let _ = blacklist_out.flush();
            }

            let _ = writeln!(out, "TRUST,{},{}", node_id, trust_val);
            let _ = out.flush();

            let _ = writeln!(
                metrics,
                "{},{},{},{:.4},{:.4},{:.4},{:.4},{}",
                node_id,
                delta_success,
                delta_dropped,
                st.ewma,
                bayes,
                beta,
                trust_value,
                trust_val
            );
            let _ = metrics.flush();

            if node_id == cfg.attacker_id {
                attacker_udp_total += delta_udp;
                attacker_udp_dropped += delta_dropped;
            }

            if let Some(file) = exposure_out.as_mut() {
                if e1_den > 0 {
                    let e1 = (e1_num as f64) * 100.0 / (e1_den as f64);
                    let e3 = if total_parent_samples > 0 {
                        (total_parent_attacker as f64) * 100.0 / (total_parent_samples as f64)
                    } else {
                        0.0
                    };
                    let e3_num = total_parent_attacker;
                    let e3_den = total_parent_samples;
                    let _ = writeln!(
                        file,
                        "{},{},{},{},{},{},{:.2},{},{},{:.2},{},{},{}",
                        line_idx,
                        total_tx,
                        attacker_udp_total,
                        attacker_udp_dropped,
                        total_parent_samples,
                        total_parent_attacker,
                        e1,
                        e1_num,
                        e1_den,
                        e3,
                        e3_num,
                        e3_den,
                        cfg.attacker_id
                    );
                    let _ = file.flush();
                }
            }

            if let Some(file) = stats_out.as_mut() {
                if cfg.stats_interval > 0 && (line_idx % cfg.stats_interval == 0) {
                    let e1 = if e1_den > 0 {
                        (e1_num as f64) * 100.0 / (e1_den as f64)
                    } else { 0.0 };
                    let e3 = if total_parent_samples > 0 {
                        (total_parent_attacker as f64) * 100.0 / (total_parent_samples as f64)
                    } else { 0.0 };
                    let e3_num = total_parent_attacker;
                    let e3_den = total_parent_samples;
                    let mut total_changes = 0u64;
                    let mut total_pairs = 0u64;
                    for st in parent_states.values() {
                        if st.samples > 1 {
                            total_changes += st.changes;
                            total_pairs += st.samples - 1;
                        }
                    }
                    let switch_rate = if total_pairs > 0 {
                        (total_changes as f64) / (total_pairs as f64)
                    } else { 0.0 };
                    let _ = writeln!(
                        file,
                        "{},{},{},{},{},{},{:.2},{},{},{:.2},{},{},{:.4}",
                        line_idx,
                        total_tx,
                        attacker_udp_total,
                        attacker_udp_dropped,
                        total_parent_samples,
                        total_parent_attacker,
                        e1,
                        e1_num,
                        e1_den,
                        e3,
                        e3_num,
                        e3_den,
                        switch_rate
                    );
                    let _ = file.flush();
                }
            }

            continue;
        }

        if trimmed.starts_with("CSV,ROUTING,") {
            let parts: Vec<&str> = trimmed.split(',').collect();
            if parts.len() < 5 {
                continue;
            }
            let joined: u8 = match parts[3].parse() {
                Ok(v) => v,
                Err(_) => continue,
            };
            if joined == 1 {
                let parent_ip = parts[4];
                total_parent_samples += 1;
                if let Some(parent_id) = parse_node_id(parent_ip) {
                    if parent_id == cfg.attacker_id {
                        total_parent_attacker += 1;
                    }
                }
            }
            continue;
        }

        if trimmed.starts_with("CSV,PARENT,") {
            let parts: Vec<&str> = trimmed.split(',').collect();
            if parts.len() < 4 {
                continue;
            }
            let node_id: u16 = match parts[2].parse() {
                Ok(v) => v,
                Err(_) => continue,
            };
            let parent_ip = parts[3];
            let st = parent_states.entry(node_id).or_default();
            st.samples += 1;
            if let Some(prev) = &st.last_parent {
                if prev != parent_ip {
                    st.changes += 1;
                }
            }
            st.last_parent = Some(parent_ip.to_string());
            continue;
        }
    }

    if let Some(file) = parent_out.as_mut() {
        eprintln!("parent_states size={}", parent_states.len());
        for (node_id, st) in parent_states.iter() {
            let rate = if st.samples > 1 {
                (st.changes as f64) / ((st.samples - 1) as f64)
            } else { 0.0 };
            let _ = writeln!(file, "{},{},{},{:.4}", node_id, st.samples, st.changes, rate);
        }
        let _ = file.flush();
    }

    if let Some(file) = final_out.as_mut() {
        for (node_id, st) in states.iter() {
            let trust_val = match cfg.metric.as_str() {
                "bayes" => ((1.0 + st.succ as f64) / (2.0 + st.succ as f64 + st.fail as f64)) * TRUST_SCALE,
                "beta" => ((cfg.beta_a + st.succ as f64)
                    / (cfg.beta_a + cfg.beta_b + st.succ as f64 + st.fail as f64)) * TRUST_SCALE,
                _ => st.ewma * TRUST_SCALE,
            };
            let trust_value = trust_val / TRUST_SCALE;
            let _ = writeln!(file, "TRUST_FINAL: node={} T={:.3}", node_id, trust_value);
        }
        let _ = file.flush();
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

    writeln!(metrics, "node_id,success,failed,ewma,bayes,beta,trust_value,trust_raw")?;

    let mut blacklist_out = OpenOptions::new()
        .create(true)
        .write(true)
        .truncate(true)
        .open(&cfg.blacklist_out)?;
    writeln!(blacklist_out, "node_id,success,failed,ewma,bayes,beta,trust_value,trust_raw")?;

    let mut exposure_out = if cfg.exposure_out.is_empty() {
        None
    } else {
        let mut f = OpenOptions::new()
            .create(true)
            .write(true)
            .truncate(true)
            .open(&cfg.exposure_out)?;
        writeln!(
            f,
            "line,tx_total,attacker_udp_total,attacker_udp_dropped,parent_samples,parent_attacker_samples,e1,e1_num,e1_den,e3,e3_num,e3_den,attacker_id"
        )?;
        Some(f)
    };

    let mut parent_out = if cfg.parent_out.is_empty() {
        None
    } else {
        let mut f = OpenOptions::new()
            .create(true)
            .write(true)
            .truncate(true)
            .open(&cfg.parent_out)?;
        writeln!(f, "node_id,parent_samples,parent_changes,switch_rate")?;
        Some(f)
    };

    let mut stats_out = if cfg.stats_out.is_empty() {
        None
    } else {
        let mut f = OpenOptions::new()
            .create(true)
            .write(true)
            .truncate(true)
            .open(&cfg.stats_out)?;
        writeln!(
            f,
            "line,tx_total,attacker_udp_total,attacker_udp_dropped,parent_samples,parent_attacker_samples,e1,e1_num,e1_den,e3,e3_num,e3_den,parent_switch_rate"
        )?;
        Some(f)
    };

    let mut final_out = if cfg.final_out.is_empty() {
        None
    } else {
        let f = OpenOptions::new()
            .create(true)
            .write(true)
            .truncate(true)
            .open(&cfg.final_out)?;
        Some(f)
    };

    if let Some(sock) = &cfg.serial_socket {
        let mut parts = sock.split(':');
        let host = parts.next().unwrap_or("127.0.0.1");
        let port = parts.next().unwrap_or("60001");
        let addr = format!("{}:{}", host, port);
        let stream = std::net::TcpStream::connect(addr)?;
        stream.set_nodelay(true).ok();
        let reader = BufReader::new(stream);
        let mut blacklist: HashMap<u16, bool> = HashMap::new();
        process_reader(
            reader,
            &cfg,
            &mut out,
            &mut metrics,
            &mut blacklist,
            &mut blacklist_out,
            &mut exposure_out,
            &mut parent_out,
            &mut stats_out,
            &mut final_out,
        )?;
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
        process_reader(
            reader,
            &cfg,
            &mut out,
            &mut metrics,
            &mut blacklist,
            &mut blacklist_out,
            &mut exposure_out,
            &mut parent_out,
            &mut stats_out,
            &mut final_out,
        )?;
    }

    Ok(())
}
