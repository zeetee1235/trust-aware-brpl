#!/usr/bin/env python3
import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]


def remove_serial_socket_plugin(contents):
    output_lines = []
    in_plugin = False
    plugin_lines = []
    skip_plugin = False
    for line in contents.splitlines(keepends=True):
        if "<plugin>" in line:
            in_plugin = True
            plugin_lines = [line]
            skip_plugin = False
            continue
        if in_plugin:
            plugin_lines.append(line)
            if "org.contikios.cooja.serialsocket.SerialSocketServer" in line:
                skip_plugin = True
            if "</plugin>" in line:
                if not skip_plugin:
                    output_lines.extend(plugin_lines)
                in_plugin = False
                plugin_lines = []
            continue
        output_lines.append(line)
    if in_plugin and not skip_plugin:
        output_lines.extend(plugin_lines)
    return "".join(output_lines)


def apply_replacements(contents, replacements):
    for pattern, repl in replacements:
        contents = re.sub(pattern, repl, contents)
    return contents


def update_trust_defines(contents, trust_lambda, trust_gamma):
    if "TRUST_GAMMA=" in contents:
        contents = re.sub(r"TRUST_GAMMA=\d+", f"TRUST_GAMMA={trust_gamma}", contents)
    else:
        contents = re.sub(
            r"TRUST_LAMBDA=(\d+)",
            f"TRUST_LAMBDA={trust_lambda},TRUST_GAMMA={trust_gamma}",
            contents,
        )
    contents = re.sub(r"TRUST_LAMBDA=\d+", f"TRUST_LAMBDA={trust_lambda}", contents)
    contents = re.sub(
        r"TRUST_PENALTY_GAMMA=\d+", f"TRUST_PENALTY_GAMMA={trust_gamma}", contents
    )
    contents = re.sub(
        r"TRUST_LAMBDA_CONF=\d+", f"TRUST_LAMBDA_CONF={trust_lambda}", contents
    )
    contents = re.sub(
        r"TRUST_PENALTY_GAMMA_CONF=\d+",
        f"TRUST_PENALTY_GAMMA_CONF={trust_gamma}",
        contents,
    )
    return contents


def build_run_name(topo_name, scenario, attack_rate, trust, lam, gam, seed):
    lam_str = "NA" if lam is None else str(lam)
    gam_str = "NA" if gam is None else str(gam)
    return (
        f"{topo_name}_{scenario}_atk{attack_rate:02d}_trust{trust}_"
        f"lam{lam_str}_gam{gam_str}_s{seed}"
    )


def write_run_meta(log_dir, meta):
    log_dir.mkdir(parents=True, exist_ok=True)
    meta_path = log_dir / "run_meta.json"
    with meta_path.open("w") as handle:
        json.dump(meta, handle, indent=2)


def run_simulation(args, combo, results_dir):
    topo_path = Path(combo["topology"])
    topo_name = topo_path.stem
    run_name = build_run_name(
        topo_name,
        combo["scenario"],
        combo["attack_rate"],
        combo["trust"],
        combo["lambda"],
        combo["gamma"],
        combo["seed"],
    )
    run_dir = results_dir / run_name
    log_dir = run_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    meta = {
        "run": run_name,
        "topology": topo_name,
        "scenario": combo["scenario"],
        "attack_rate": combo["attack_rate"],
        "trust": combo["trust"],
        "lambda": combo["lambda"],
        "gamma": combo["gamma"],
        "seed": combo["seed"],
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    write_run_meta(log_dir, meta)

    if args.dry_run:
        return run_name, "planned"

    trust_engine = PROJECT_DIR / "tools" / "trust_engine" / "target" / "release" / "trust_engine"
    if not trust_engine.exists():
        raise RuntimeError("trust_engine binary missing; build it in tools/trust_engine first.")

    temp_config = PROJECT_DIR / "configs" / f"temp_{run_name}.csc"
    sim_time_ms = int(args.sim_time * 1000)
    trust_feedback = run_dir / "trust_feedback.txt"

    contents = topo_path.read_text()
    contents = apply_replacements(
        contents,
        [
            (r"<randomseed>\d+</randomseed>", f"<randomseed>{combo['seed']}</randomseed>"),
            (r"@SIM_TIME_MS@", str(sim_time_ms)),
            (r"@SIM_TIME_SEC@", str(args.sim_time)),
            (r"@TRUST_FEEDBACK_PATH@", str(trust_feedback)),
            (r"BRPL_MODE=\d", "BRPL_MODE=1"),
            (r"TRUST_ENABLED=\d", f"TRUST_ENABLED={combo['trust']}"),
            (r"ATTACK_DROP_PCT=\d+", f"ATTACK_DROP_PCT={combo['attack_rate']}"),
            (r"SEND_INTERVAL_SECONDS=\d+", f"SEND_INTERVAL_SECONDS={args.send_interval}"),
            (r"WARMUP_SECONDS=\d+", f"WARMUP_SECONDS={args.warmup}"),
            (r",PROJECT_CONF_PATH=[^,< ]+", ""),
            (r",PROJECT_CONF_PATH=\"[^\"]+\"", ""),
        ],
    )
    trust_lambda = combo["lambda"] if combo["lambda"] is not None else 0
    trust_gamma = combo["gamma"] if combo["gamma"] is not None else 1
    contents = update_trust_defines(contents, trust_lambda, trust_gamma)
    contents = remove_serial_socket_plugin(contents)
    temp_config.write_text(contents)

    if args.clean_build:
        shutil.rmtree(PROJECT_DIR / "motes" / "build", ignore_errors=True)

    trust_feedback.touch(exist_ok=True)
    (log_dir / "COOJA.testlog").touch(exist_ok=True)

    trust_engine_cmd = [
        str(trust_engine),
        "--input",
        str(log_dir / "COOJA.testlog"),
        "--output",
        str(trust_feedback),
        "--metrics-out",
        str(run_dir / "trust_metrics.csv"),
        "--blacklist-out",
        str(run_dir / "blacklist.csv"),
        "--exposure-out",
        str(run_dir / "exposure.csv"),
        "--parent-out",
        str(run_dir / "parent_switch.csv"),
        "--stats-out",
        str(run_dir / "stats.csv"),
        "--stats-interval",
        "200",
        "--metric",
        "ewma",
        "--alpha",
        "0.2",
        "--ewma-min",
        "0.7",
        "--miss-threshold",
        "5",
        "--forwarders-only",
        "--fwd-drop-threshold",
        "0.2",
        "--attacker-id",
        "2",
        "--follow",
    ]
    trust_engine_log = (run_dir / "trust_engine.log").open("w")
    trust_proc = subprocess.Popen(trust_engine_cmd, stdout=trust_engine_log, stderr=subprocess.STDOUT)

    env = os.environ.copy()
    env["CONTIKI_NG_PATH"] = str(args.contiki_path)
    env["COOJA_PATH"] = str(args.cooja_path)
    env["SERIAL_SOCKET_DISABLE"] = "1"
    env["JAVA_OPTS"] = args.java_opts

    cooja_cmd = [
        "java",
        "--enable-preview",
        *args.java_opts.split(),
        "-jar",
        str(Path(args.cooja_path) / "tools" / "cooja" / "build" / "libs" / "cooja.jar"),
        "--no-gui",
        "--autostart",
        f"--contiki={args.contiki_path}",
        f"--logdir={log_dir}",
        str(temp_config),
    ]

    status = "completed"
    try:
        with (run_dir / "cooja_output.log").open("w") as handle:
            subprocess.run(
                cooja_cmd,
                stdout=handle,
                stderr=subprocess.STDOUT,
                env=env,
                timeout=args.timeout,
                check=True,
            )
    except subprocess.TimeoutExpired:
        status = "timeout"
    except subprocess.CalledProcessError:
        status = "failed"
    finally:
        trust_proc.terminate()
        try:
            trust_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            trust_proc.kill()
        trust_engine_log.close()
        temp_config.unlink(missing_ok=True)

    return run_name, status


def generate_combos(args, topologies):
    attack_rates = [30, 50]
    if args.include_attack_extremes:
        attack_rates = [0, 30, 50, 70]
    seeds = args.seeds
    lambda_set = [0, 1, 3, 10]
    gamma_set = [1, 2, 4]
    combos = []

    for topo in topologies:
        topo_name = Path(topo).stem
        for attack_rate in attack_rates:
            scenario = "normal" if attack_rate == 0 else "attack"
            for seed in seeds:
                combos.append(
                    {
                        "topology": topo,
                        "topo_name": topo_name,
                        "scenario": scenario,
                        "attack_rate": attack_rate,
                        "trust": 0,
                        "lambda": None,
                        "gamma": None,
                        "seed": seed,
                    }
                )
            if attack_rate == 0:
                if args.include_normal_sanity:
                    for (lam, gam) in [(0, 1), (3, 2)]:
                        for seed in seeds:
                            combos.append(
                                {
                                    "topology": topo,
                                    "topo_name": topo_name,
                                    "scenario": scenario,
                                    "attack_rate": attack_rate,
                                    "trust": 1,
                                    "lambda": lam,
                                    "gamma": gam,
                                    "seed": seed,
                                }
                            )
                continue
            for lam in lambda_set:
                for gam in gamma_set:
                    for seed in seeds:
                        combos.append(
                            {
                                "topology": topo,
                                "topo_name": topo_name,
                                "scenario": scenario,
                                "attack_rate": attack_rate,
                                "trust": 1,
                                "lambda": lam,
                                "gamma": gam,
                                "seed": seed,
                            }
                        )

    return combos


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Only create sweep matrix")
    parser.add_argument("--include-attack-extremes", action="store_true", help="Add 0/70 attack rates")
    parser.add_argument("--include-control-topology", action="store_true", help="Include T2_random_15_seed1")
    parser.add_argument("--include-normal-sanity", action="store_true", help="Run trust-on sanity for attack=0")
    parser.add_argument("--seeds", nargs="+", type=int, default=[111111, 222222, 333333, 444444, 555555])
    parser.add_argument("--sim-time", type=int, default=600)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--send-interval", type=int, default=30)
    parser.add_argument("--warmup", type=int, default=120)
    parser.add_argument("--clean-build", action="store_true")
    parser.add_argument("--contiki-path", default=str(PROJECT_DIR / "contiki-ng-brpl"))
    parser.add_argument("--cooja-path", default="/home/dev/contiki-ng")
    parser.add_argument("--java-opts", default="-Xmx4G -Xms2G")
    args = parser.parse_args()

    topologies = [
        str(PROJECT_DIR / "configs" / "topologies" / "T3.csc"),
        str(PROJECT_DIR / "configs" / "topologies" / "T1_S.csc"),
    ]
    if args.include_control_topology:
        topologies.append(str(PROJECT_DIR / "configs" / "topologies" / "T2_random_15_seed1.csc"))

    combos = generate_combos(args, topologies)

    timestamp = time.strftime("%Y%m%d-%H%M%S")
    results_dir = PROJECT_DIR / "results" / f"experiments-{timestamp}"
    results_dir.mkdir(parents=True, exist_ok=True)

    matrix_path = results_dir / "sweep_matrix.csv"
    matrix_rows = []
    for combo in combos:
        topo_name = Path(combo["topology"]).stem
        run_name = build_run_name(
            topo_name,
            combo["scenario"],
            combo["attack_rate"],
            combo["trust"],
            combo["lambda"],
            combo["gamma"],
            combo["seed"],
        )
        matrix_rows.append(
            {
                "run": run_name,
                "topology": topo_name,
                "scenario": combo["scenario"],
                "attack_rate": combo["attack_rate"],
                "trust": combo["trust"],
                "lambda": combo["lambda"] if combo["lambda"] is not None else "NA",
                "gamma": combo["gamma"] if combo["gamma"] is not None else "NA",
                "seed": combo["seed"],
                "status": "planned",
            }
        )
    with matrix_path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            [
                "run",
                "topology",
                "scenario",
                "attack_rate",
                "trust",
                "lambda",
                "gamma",
                "seed",
                "status",
            ],
        )
        writer.writeheader()
        writer.writerows(matrix_rows)

    statuses = {}
    for combo in combos:
        run_name, status = run_simulation(args, combo, results_dir)
        statuses[run_name] = status
        if args.dry_run:
            continue

    if not args.dry_run:
        with matrix_path.open(errors="ignore") as handle:
            reader = csv.DictReader(handle)
            rows = []
            for row in reader:
                row["status"] = statuses.get(row["run"], row["status"])
                rows.append(row)
        with matrix_path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

        summary_cmd = [
            sys.executable,
            str(PROJECT_DIR / "scripts" / "experiment_summary.py"),
            str(results_dir),
            "--matrix",
            str(matrix_path),
        ]
        subprocess.run(summary_cmd, check=False)

    print(str(results_dir))


if __name__ == "__main__":
    main()
