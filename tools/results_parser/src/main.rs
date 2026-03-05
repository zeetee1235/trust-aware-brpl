use std::collections::HashMap;
use std::env;
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone)]
struct RunMeta {
    run_name: String,
    topology_family: String,
    topology_scale: String,
    node_count: Option<u32>,
    routing: String,
    traffic: String,
    trust_label: String,
    trust_on: u8,
    attack_rate: Option<u32>,
    attack_mode: Option<u32>,
    sink_delta: Option<u32>,
    trust_alpha: Option<f64>,
    trust_lambda: Option<u32>,
    trust_gamma: Option<u32>,
    seed: Option<u64>,
}

#[derive(Debug, Default, Clone)]
struct Exposure {
    tx_total: Option<f64>,
    attacker_udp_total: Option<f64>,
    attacker_udp_dropped: Option<f64>,
    parent_samples: Option<f64>,
    parent_attacker_samples: Option<f64>,
    e1: Option<f64>,
    e1_num: Option<f64>,
    e1_den: Option<f64>,
    e3: Option<f64>,
    e3_num: Option<f64>,
    e3_den: Option<f64>,
    attacker_id: Option<u32>,
}

#[derive(Debug, Clone)]
struct RunRecord {
    meta: RunMeta,
    run_dir: String,
    status: String,
    has_test_ok: bool,
    has_cooja_output: bool,
    has_testlog: bool,
    cooja_output_bytes: u64,
    testlog_bytes: u64,
    trust_metrics_rows: u64,
    blacklist_rows: u64,
    trust_final_rows: u64,
    min_final_trust: Option<f64>,
    max_final_trust: Option<f64>,
    exp: Exposure,
}

#[derive(Default, Debug)]
struct Agg {
    count: u64,
    e1_sum: f64,
    e1_n: u64,
    e3_sum: f64,
    e3_n: u64,
    tx_sum: f64,
    tx_n: u64,
    drop_sum: f64,
    drop_n: u64,
}

#[derive(Debug)]
struct Cli {
    input: PathBuf,
    output_dir: PathBuf,
    runs_csv: String,
    summary_csv: String,
}

fn usage() {
    eprintln!(
        "Usage: results_parser --input <results_dir> [--output-dir <dir>] [--runs-csv <name>] [--summary-csv <name>]"
    );
}

fn parse_args() -> Result<Cli, String> {
    let mut input: Option<PathBuf> = None;
    let mut output_dir: Option<PathBuf> = None;
    let mut runs_csv = String::from("runs.csv");
    let mut summary_csv = String::from("summary.csv");

    let args: Vec<String> = env::args().skip(1).collect();
    let mut i = 0;
    while i < args.len() {
        match args[i].as_str() {
            "--input" => {
                i += 1;
                if i >= args.len() {
                    return Err("Missing value for --input".to_string());
                }
                input = Some(PathBuf::from(&args[i]));
            }
            "--output-dir" => {
                i += 1;
                if i >= args.len() {
                    return Err("Missing value for --output-dir".to_string());
                }
                output_dir = Some(PathBuf::from(&args[i]));
            }
            "--runs-csv" => {
                i += 1;
                if i >= args.len() {
                    return Err("Missing value for --runs-csv".to_string());
                }
                runs_csv = args[i].clone();
            }
            "--summary-csv" => {
                i += 1;
                if i >= args.len() {
                    return Err("Missing value for --summary-csv".to_string());
                }
                summary_csv = args[i].clone();
            }
            other => {
                return Err(format!("Unknown argument: {other}"));
            }
        }
        i += 1;
    }

    let input = input.ok_or_else(|| "--input is required".to_string())?;
    let output_dir = output_dir.unwrap_or_else(|| input.join("parsed"));

    Ok(Cli {
        input,
        output_dir,
        runs_csv,
        summary_csv,
    })
}

fn parse_prefixed_u32(token: &str, prefix: &str) -> Option<u32> {
    token.strip_prefix(prefix)?.parse::<u32>().ok()
}

fn parse_prefixed_u64(token: &str, prefix: &str) -> Option<u64> {
    token.strip_prefix(prefix)?.parse::<u64>().ok()
}

fn parse_prefixed_f64(token: &str, prefix: &str) -> Option<f64> {
    token.strip_prefix(prefix)?.parse::<f64>().ok()
}

fn parse_run_name(run_name: &str) -> RunMeta {
    let parts: Vec<&str> = run_name.split('_').collect();

    let topology_family = parts.first().unwrap_or(&"UNKNOWN").to_string();
    let topology_scale = parts.get(1).unwrap_or(&"NA").to_string();
    let node_count = parts.get(2).and_then(|v| v.parse::<u32>().ok());
    let routing = parts.get(3).unwrap_or(&"unknown").to_string();
    let traffic = parts.get(4).unwrap_or(&"unknown").to_string();
    let trust_label = parts.get(5).unwrap_or(&"unknown").to_string();
    let trust_on = u8::from(trust_label == "trust");

    let mut attack_rate = None;
    let mut attack_mode = None;
    let mut sink_delta = None;
    let mut trust_alpha = None;
    let mut trust_lambda = None;
    let mut trust_gamma = None;
    let mut seed = None;

    for token in &parts {
        if attack_rate.is_none() {
            attack_rate = parse_prefixed_u32(token, "p");
        }
        if attack_mode.is_none() {
            attack_mode = parse_prefixed_u32(token, "mode");
        }
        if sink_delta.is_none() {
            sink_delta = parse_prefixed_u32(token, "d");
        }
        if trust_alpha.is_none() {
            trust_alpha = parse_prefixed_f64(token, "a");
        }
        if trust_lambda.is_none() {
            trust_lambda = parse_prefixed_u32(token, "lam");
        }
        if trust_gamma.is_none() {
            trust_gamma = parse_prefixed_u32(token, "gam");
        }
        if seed.is_none() {
            seed = parse_prefixed_u64(token, "s");
        }
    }

    RunMeta {
        run_name: run_name.to_string(),
        topology_family,
        topology_scale,
        node_count,
        routing,
        traffic,
        trust_label,
        trust_on,
        attack_rate,
        attack_mode,
        sink_delta,
        trust_alpha,
        trust_lambda,
        trust_gamma,
        seed,
    }
}

fn parse_status(cooja_output_path: &Path) -> (String, bool, u64) {
    let mut status = "missing".to_string();
    let mut has_test_ok = false;
    let bytes = fs::metadata(cooja_output_path).map(|m| m.len()).unwrap_or(0);

    if let Ok(text) = fs::read_to_string(cooja_output_path) {
        status = "unknown".to_string();
        if text.contains("TEST OK") {
            has_test_ok = true;
            status = "ok".to_string();
        } else if text.contains("Simulation failed")
            || text.contains("Exception")
            || text.contains("ERROR")
            || text.contains("timed out")
        {
            status = "failed".to_string();
        }
    }

    (status, has_test_ok, bytes)
}

fn parse_exposure(path: &Path) -> Exposure {
    let mut out = Exposure::default();
    let Ok(text) = fs::read_to_string(path) else {
        return out;
    };

    for line in text.lines().rev() {
        let cols: Vec<&str> = line.split(',').collect();
        if cols.len() < 13 {
            continue;
        }
        if !cols[0].chars().all(|c| c.is_ascii_digit()) {
            continue;
        }

        let parse = |idx: usize| cols.get(idx).and_then(|v| v.parse::<f64>().ok());
        out.tx_total = parse(1);
        out.attacker_udp_total = parse(2);
        out.attacker_udp_dropped = parse(3);
        out.parent_samples = parse(4);
        out.parent_attacker_samples = parse(5);
        out.e1 = parse(6);
        out.e1_num = parse(7);
        out.e1_den = parse(8);
        out.e3 = parse(9);
        out.e3_num = parse(10);
        out.e3_den = parse(11);
        out.attacker_id = cols.get(12).and_then(|v| v.parse::<u32>().ok());
        break;
    }

    out
}

fn parse_trust_final(path: &Path) -> (u64, Option<f64>, Option<f64>) {
    let Ok(text) = fs::read_to_string(path) else {
        return (0, None, None);
    };

    let mut count = 0_u64;
    let mut min_t: Option<f64> = None;
    let mut max_t: Option<f64> = None;

    for line in text.lines() {
        if let Some(pos) = line.find("T=") {
            if let Ok(val) = line[(pos + 2)..].trim().parse::<f64>() {
                count += 1;
                min_t = Some(min_t.map_or(val, |m| m.min(val)));
                max_t = Some(max_t.map_or(val, |m| m.max(val)));
            }
        }
    }

    (count, min_t, max_t)
}

fn count_data_rows(path: &Path) -> u64 {
    let Ok(text) = fs::read_to_string(path) else {
        return 0;
    };

    text.lines()
        .filter(|line| {
            let first = line.split(',').next().unwrap_or("");
            first.chars().next().map(|c| c.is_ascii_digit()).unwrap_or(false)
        })
        .count() as u64
}

fn csv_escape(s: &str) -> String {
    if s.contains(',') || s.contains('"') || s.contains('\n') {
        format!("\"{}\"", s.replace('"', "\"\""))
    } else {
        s.to_string()
    }
}

fn opt_to_string<T: ToString>(v: &Option<T>) -> String {
    v.as_ref().map(ToString::to_string).unwrap_or_default()
}

fn f64_opt_to_string(v: Option<f64>) -> String {
    v.map(|x| format!("{x:.6}")).unwrap_or_default()
}

fn write_csv_line(file: &mut fs::File, fields: &[String]) -> Result<(), Box<dyn std::error::Error>> {
    let line = fields
        .iter()
        .map(|f| csv_escape(f))
        .collect::<Vec<_>>()
        .join(",");
    writeln!(file, "{line}")?;
    Ok(())
}

fn write_runs_csv(path: &Path, runs: &[RunRecord]) -> Result<(), Box<dyn std::error::Error>> {
    let mut file = fs::File::create(path)?;

    write_csv_line(
        &mut file,
        &[
            "run_name".into(),
            "run_dir".into(),
            "status".into(),
            "has_test_ok".into(),
            "has_cooja_output".into(),
            "has_testlog".into(),
            "cooja_output_bytes".into(),
            "testlog_bytes".into(),
            "topology_family".into(),
            "topology_scale".into(),
            "node_count".into(),
            "routing".into(),
            "traffic".into(),
            "trust_label".into(),
            "trust_on".into(),
            "attack_rate".into(),
            "attack_mode".into(),
            "sink_delta".into(),
            "trust_alpha".into(),
            "trust_lambda".into(),
            "trust_gamma".into(),
            "seed".into(),
            "trust_metrics_rows".into(),
            "blacklist_rows".into(),
            "trust_final_rows".into(),
            "min_final_trust".into(),
            "max_final_trust".into(),
            "tx_total".into(),
            "attacker_udp_total".into(),
            "attacker_udp_dropped".into(),
            "parent_samples".into(),
            "parent_attacker_samples".into(),
            "e1".into(),
            "e1_num".into(),
            "e1_den".into(),
            "e3".into(),
            "e3_num".into(),
            "e3_den".into(),
            "attacker_id".into(),
        ],
    )?;

    for r in runs {
        write_csv_line(
            &mut file,
            &[
                r.meta.run_name.clone(),
                r.run_dir.clone(),
                r.status.clone(),
                if r.has_test_ok { "1" } else { "0" }.into(),
                if r.has_cooja_output { "1" } else { "0" }.into(),
                if r.has_testlog { "1" } else { "0" }.into(),
                r.cooja_output_bytes.to_string(),
                r.testlog_bytes.to_string(),
                r.meta.topology_family.clone(),
                r.meta.topology_scale.clone(),
                opt_to_string(&r.meta.node_count),
                r.meta.routing.clone(),
                r.meta.traffic.clone(),
                r.meta.trust_label.clone(),
                r.meta.trust_on.to_string(),
                opt_to_string(&r.meta.attack_rate),
                opt_to_string(&r.meta.attack_mode),
                opt_to_string(&r.meta.sink_delta),
                opt_to_string(&r.meta.trust_alpha),
                opt_to_string(&r.meta.trust_lambda),
                opt_to_string(&r.meta.trust_gamma),
                opt_to_string(&r.meta.seed),
                r.trust_metrics_rows.to_string(),
                r.blacklist_rows.to_string(),
                r.trust_final_rows.to_string(),
                f64_opt_to_string(r.min_final_trust),
                f64_opt_to_string(r.max_final_trust),
                f64_opt_to_string(r.exp.tx_total),
                f64_opt_to_string(r.exp.attacker_udp_total),
                f64_opt_to_string(r.exp.attacker_udp_dropped),
                f64_opt_to_string(r.exp.parent_samples),
                f64_opt_to_string(r.exp.parent_attacker_samples),
                f64_opt_to_string(r.exp.e1),
                f64_opt_to_string(r.exp.e1_num),
                f64_opt_to_string(r.exp.e1_den),
                f64_opt_to_string(r.exp.e3),
                f64_opt_to_string(r.exp.e3_num),
                f64_opt_to_string(r.exp.e3_den),
                opt_to_string(&r.exp.attacker_id),
            ],
        )?;
    }

    Ok(())
}

fn write_summary_csv(path: &Path, runs: &[RunRecord]) -> Result<(), Box<dyn std::error::Error>> {
    let mut map: HashMap<String, Agg> = HashMap::new();

    for r in runs {
        let key = format!(
            "{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}",
            r.meta.topology_family,
            r.meta.topology_scale,
            r.meta.routing,
            r.meta.traffic,
            r.meta.trust_on,
            opt_to_string(&r.meta.attack_rate),
            opt_to_string(&r.meta.attack_mode),
            opt_to_string(&r.meta.sink_delta),
            opt_to_string(&r.meta.trust_alpha),
            opt_to_string(&r.meta.trust_lambda),
            opt_to_string(&r.meta.trust_gamma)
        );

        let e = map.entry(key).or_default();
        e.count += 1;

        if let Some(v) = r.exp.e1 {
            e.e1_sum += v;
            e.e1_n += 1;
        }
        if let Some(v) = r.exp.e3 {
            e.e3_sum += v;
            e.e3_n += 1;
        }
        if let Some(v) = r.exp.tx_total {
            e.tx_sum += v;
            e.tx_n += 1;
        }
        if let Some(v) = r.exp.attacker_udp_dropped {
            e.drop_sum += v;
            e.drop_n += 1;
        }
    }

    let mut file = fs::File::create(path)?;
    write_csv_line(
        &mut file,
        &[
            "topology_family".into(),
            "topology_scale".into(),
            "routing".into(),
            "traffic".into(),
            "trust_on".into(),
            "attack_rate".into(),
            "attack_mode".into(),
            "sink_delta".into(),
            "trust_alpha".into(),
            "trust_lambda".into(),
            "trust_gamma".into(),
            "run_count".into(),
            "mean_e1".into(),
            "mean_e3".into(),
            "mean_tx_total".into(),
            "mean_attacker_udp_dropped".into(),
        ],
    )?;

    let mut keys: Vec<_> = map.keys().cloned().collect();
    keys.sort();

    for k in keys {
        let cols: Vec<&str> = k.split('|').collect();
        let a = map.get(&k).expect("aggregated key must exist");

        let mean_e1 = if a.e1_n > 0 {
            format!("{:.6}", a.e1_sum / a.e1_n as f64)
        } else {
            String::new()
        };
        let mean_e3 = if a.e3_n > 0 {
            format!("{:.6}", a.e3_sum / a.e3_n as f64)
        } else {
            String::new()
        };
        let mean_tx = if a.tx_n > 0 {
            format!("{:.6}", a.tx_sum / a.tx_n as f64)
        } else {
            String::new()
        };
        let mean_drop = if a.drop_n > 0 {
            format!("{:.6}", a.drop_sum / a.drop_n as f64)
        } else {
            String::new()
        };

        write_csv_line(
            &mut file,
            &[
                cols.first().unwrap_or(&"").to_string(),
                cols.get(1).unwrap_or(&"").to_string(),
                cols.get(2).unwrap_or(&"").to_string(),
                cols.get(3).unwrap_or(&"").to_string(),
                cols.get(4).unwrap_or(&"").to_string(),
                cols.get(5).unwrap_or(&"").to_string(),
                cols.get(6).unwrap_or(&"").to_string(),
                cols.get(7).unwrap_or(&"").to_string(),
                cols.get(8).unwrap_or(&"").to_string(),
                cols.get(9).unwrap_or(&"").to_string(),
                cols.get(10).unwrap_or(&"").to_string(),
                a.count.to_string(),
                mean_e1,
                mean_e3,
                mean_tx,
                mean_drop,
            ],
        )?;
    }

    Ok(())
}

fn collect_runs(input: &Path) -> Vec<RunRecord> {
    let mut runs = Vec::new();

    let Ok(entries) = fs::read_dir(input) else {
        return runs;
    };

    for entry in entries.flatten() {
        let path = entry.path();
        if !path.is_dir() {
            continue;
        }

        let run_name = match path.file_name().and_then(|s| s.to_str()) {
            Some(v) => v,
            None => continue,
        };

        if run_name == "worker_logs" || run_name == "parsed" {
            continue;
        }

        let cooja_output = path.join("cooja_output.log");
        let testlog = path.join("logs").join("COOJA.testlog");
        // Ignore non-run helper directories inside results/
        if !cooja_output.exists() && !testlog.exists() {
            continue;
        }

        let meta = parse_run_name(run_name);

        let exposure = path.join("exposure.csv");
        let trust_metrics = path.join("trust_metrics.csv");
        let blacklist = path.join("blacklist.csv");
        let trust_final = path.join("trust_final.log");

        let has_cooja_output = cooja_output.exists();
        let has_testlog = testlog.exists();

        let (status, has_test_ok, cooja_output_bytes) = if has_cooja_output {
            parse_status(&cooja_output)
        } else {
            ("missing".to_string(), false, 0)
        };

        let testlog_bytes = fs::metadata(&testlog).map(|m| m.len()).unwrap_or(0);
        let exp = parse_exposure(&exposure);
        let trust_metrics_rows = count_data_rows(&trust_metrics);
        let blacklist_rows = count_data_rows(&blacklist);
        let (trust_final_rows, min_final_trust, max_final_trust) = parse_trust_final(&trust_final);

        runs.push(RunRecord {
            meta,
            run_dir: path.to_string_lossy().to_string(),
            status,
            has_test_ok,
            has_cooja_output,
            has_testlog,
            cooja_output_bytes,
            testlog_bytes,
            trust_metrics_rows,
            blacklist_rows,
            trust_final_rows,
            min_final_trust,
            max_final_trust,
            exp,
        });
    }

    runs.sort_by(|a, b| a.meta.run_name.cmp(&b.meta.run_name));
    runs
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let cli = match parse_args() {
        Ok(c) => c,
        Err(e) => {
            usage();
            return Err(e.into());
        }
    };

    fs::create_dir_all(&cli.output_dir)?;

    let runs = collect_runs(&cli.input);

    let runs_path = cli.output_dir.join(cli.runs_csv);
    let summary_path = cli.output_dir.join(cli.summary_csv);

    write_runs_csv(&runs_path, &runs)?;
    write_summary_csv(&summary_path, &runs)?;

    let ok_count = runs.iter().filter(|r| r.status == "ok").count();
    let fail_count = runs.iter().filter(|r| r.status == "failed").count();

    println!("Parsed {} runs", runs.len());
    println!("  ok: {}", ok_count);
    println!("  failed: {}", fail_count);
    println!("  output: {}", runs_path.display());
    println!("  output: {}", summary_path.display());

    Ok(())
}
