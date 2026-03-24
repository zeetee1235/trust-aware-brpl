#!/usr/bin/env python3
"""Rich live dashboard for all-sweep monitoring."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from rich.console import Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn
from rich.table import Table
from rich.text import Text


class SystemSampler:
    def __init__(self) -> None:
        self.prev_total: Optional[int] = None
        self.prev_idle: Optional[int] = None

    @staticmethod
    def _read_cpu_times() -> Tuple[int, int]:
        with open("/proc/stat", "r", encoding="utf-8", errors="replace") as f:
            first = f.readline().strip()
        parts = first.split()
        nums = [int(x) for x in parts[1:]]
        total = sum(nums)
        idle = nums[3] + (nums[4] if len(nums) > 4 else 0)
        return total, idle

    @staticmethod
    def _read_mem() -> Dict[str, int]:
        out: Dict[str, int] = {}
        with open("/proc/meminfo", "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if ":" not in line:
                    continue
                k, rest = line.split(":", 1)
                m = re.search(r"(\d+)", rest)
                if m:
                    out[k.strip()] = int(m.group(1))  # kB
        return out

    @staticmethod
    def _detect_temp_c() -> Optional[float]:
        max_c: Optional[float] = None
        for raw_path in list(Path("/sys/class/thermal").glob("thermal_zone*/temp")) + list(
            Path("/sys/class/hwmon").glob("hwmon*/temp*_input")
        ):
            try:
                raw = raw_path.read_text(encoding="utf-8", errors="replace").strip()
                if not raw or not re.fullmatch(r"-?\d+", raw):
                    continue
                val = int(raw)
                c = val / 1000.0 if abs(val) >= 1000 else float(val)
                if max_c is None or c > max_c:
                    max_c = c
            except Exception:
                continue
        if max_c is not None:
            return max_c

        sensors = subprocess.run(["bash", "-lc", "command -v sensors >/dev/null 2>&1 && sensors || true"], capture_output=True, text=True)
        if sensors.returncode == 0 and sensors.stdout:
            vals: List[float] = []
            for m in re.finditer(r"([+-]?\d+(?:\.\d+)?)°C", sensors.stdout):
                try:
                    vals.append(float(m.group(1)))
                except ValueError:
                    pass
            if vals:
                return max(vals)
        return None

    def sample(self) -> Dict[str, Optional[float]]:
        t, i = self._read_cpu_times()
        cpu_pct: Optional[float] = None
        if self.prev_total is not None and self.prev_idle is not None:
            dt = t - self.prev_total
            di = i - self.prev_idle
            if dt > 0:
                cpu_pct = max(0.0, min(100.0, 100.0 * (dt - di) / dt))
        self.prev_total, self.prev_idle = t, i

        mem = self._read_mem()
        mem_total = float(mem.get("MemTotal", 0))
        mem_avail = float(mem.get("MemAvailable", 0))
        mem_used = max(0.0, mem_total - mem_avail)
        mem_pct = (mem_used / mem_total * 100.0) if mem_total > 0 else None

        swap_total = float(mem.get("SwapTotal", 0))
        swap_free = float(mem.get("SwapFree", 0))
        swap_used = max(0.0, swap_total - swap_free)
        swap_pct = (swap_used / swap_total * 100.0) if swap_total > 0 else 0.0

        temp_c = self._detect_temp_c()
        return {
            "cpu_pct": cpu_pct,
            "mem_pct": mem_pct,
            "mem_used_gib": mem_used / (1024 * 1024),
            "mem_total_gib": mem_total / (1024 * 1024),
            "swap_pct": swap_pct,
            "swap_used_gib": swap_used / (1024 * 1024),
            "swap_total_gib": swap_total / (1024 * 1024),
            "temp_c": temp_c,
        }


def evaluate_health(metrics: Dict[str, Optional[float]]) -> Tuple[str, str]:
    cpu = metrics.get("cpu_pct")
    mem = metrics.get("mem_pct")
    swap = metrics.get("swap_pct")
    temp = metrics.get("temp_c")

    danger_reasons: List[str] = []
    risky_reasons: List[str] = []

    if cpu is not None:
        if cpu >= 99:
            danger_reasons.append(f"CPU {cpu:.1f}%")
        elif cpu >= 95:
            risky_reasons.append(f"CPU {cpu:.1f}%")

    if mem is not None:
        if mem >= 98:
            danger_reasons.append(f"MEM {mem:.1f}%")
        elif mem >= 92:
            risky_reasons.append(f"MEM {mem:.1f}%")

    if swap is not None:
        if swap >= 40:
            danger_reasons.append(f"SWAP {swap:.1f}%")
        elif swap >= 10:
            risky_reasons.append(f"SWAP {swap:.1f}%")

    if temp is not None:
        if temp >= 97:
            danger_reasons.append(f"TEMP {temp:.1f}C")
        elif temp >= 90:
            risky_reasons.append(f"TEMP {temp:.1f}C")

    if danger_reasons:
        return "DANGER", ", ".join(danger_reasons)
    if risky_reasons:
        return "RISKY", ", ".join(risky_reasons)
    return "SAFE", "within thresholds"


def parse_kv_file(path: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def tail_lines(path: Path, n: int) -> List[str]:
    if n <= 0 or not path.exists():
        return []
    with path.open("rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        block = 4096
        data = b""
        while size > 0 and data.count(b"\n") <= n:
            step = min(block, size)
            size -= step
            f.seek(size)
            data = f.read(step) + data
        lines = data.decode("utf-8", errors="replace").splitlines()
        return lines[-n:]


def count_done(root: Path) -> int:
    if not root.exists():
        return 0
    return sum(1 for _ in root.rglob("done") if _.is_file())


def launcher_state(pid_file: Path) -> Tuple[str, str, str]:
    pid = "n/a"
    if pid_file.exists():
        pid = pid_file.read_text(encoding="utf-8", errors="replace").strip() or "n/a"

    if pid == "n/a":
        return pid, "no", ""

    ps = subprocess.run(["ps", "-p", pid, "-o", "args="], capture_output=True, text=True)
    if ps.returncode == 0:
        cmd = ps.stdout.strip()
        if "run_all_sweeps_once.sh" in cmd:
            return pid, "yes", cmd
        return pid, "stale", cmd

    child = subprocess.run(
        [
            "pgrep",
            "-f",
            "scripts/run_random_topo_sweep.sh|scripts/run_param_sweep_bundle.sh|scripts/run_sweep.sh|scripts/run_loss_attack_sweep.sh",
        ],
        capture_output=True,
        text=True,
    )
    if child.returncode == 0 and child.stdout.strip():
        return pid, "child-active", child.stdout.strip().replace("\n", ",")
    return pid, "no", ""


def detect_phase(log_tail: List[str]) -> str:
    text = "\n".join(log_tail)
    if "=== Running random-topology sweep" in text and "Random-topology sweep complete" not in text:
        return "random-topology"
    if any(k in text for k in ("[BASE]", "[FAMILY]", "[MATRIX]")):
        return "parameter-bundle"
    if "[DONE ]" in text:
        return "finished"
    return "starting"


def parse_run_roots(log_path: Path, limit: int) -> List[str]:
    roots: List[str] = []
    if not log_path.exists():
        return roots
    pat = re.compile(r"^Run root\s+:\s+(.*)$")
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = pat.match(line)
        if m:
            roots.append(m.group(1).strip())
    return roots[-limit:]


def count_log_matches(log_path: Path, pattern: str) -> int:
    if not log_path.exists():
        return 0
    pat = re.compile(pattern)
    cnt = 0
    with log_path.open("r", encoding="utf-8", errors="replace") as f:
        for ln in f:
            if pat.search(ln):
                cnt += 1
    return cnt


def pool_rows(roots: List[str]) -> List[Tuple[str, int, int, int, int]]:
    rows = []
    for root in roots:
        r = Path(root)
        sdir = r / "status"
        done = running = failed = queued = 0
        if sdir.exists():
            done = sum(1 for _ in (sdir / "done").glob("*") if _.is_file())
            running = sum(1 for _ in (sdir / "running").glob("*") if _.is_file())
            failed = sum(1 for _ in (sdir / "failed").glob("*") if _.is_file())
            qfiles = sorted(r.glob("queue_*.txt"), key=lambda p: p.stat().st_mtime)
            if qfiles:
                queued = sum(1 for _ in qfiles[-1].open("r", encoding="utf-8", errors="replace"))
        rows.append((root, done, running, failed, queued))
    return rows


def find_error_lines(log_path: Path, n: int) -> List[str]:
    if not log_path.exists():
        return []
    pat = re.compile(r"\[FAIL\]|\[ERROR\]|Traceback|Exception|complete with failures|ERROR:")
    lines = [ln for ln in log_path.read_text(encoding="utf-8", errors="replace").splitlines() if pat.search(ln)]
    return lines[-n:]


def failed_worker_tail(log_path: Path, nworkers: int = 2, nlines: int = 8) -> List[str]:
    roots = parse_run_roots(log_path, 1)
    if not roots:
        return ["(no run root)"]
    active = Path(roots[-1])
    failed_dir = active / "status" / "failed"
    if not failed_dir.exists():
        return ["(no failed worker status yet)"]

    failed = sorted([p for p in failed_dir.glob("*") if p.is_file()], key=lambda p: p.stat().st_mtime, reverse=True)
    if not failed:
        return ["(no failed worker status yet)"]

    out: List[str] = []
    for f in failed[:nworkers]:
        stem = f.name
        out.append(f"--- {stem} ---")
        wlog = active / "logs" / f"{stem}.log"
        if not wlog.exists():
            out.append(f"worker log missing: {wlog}")
            continue
        out.extend(tail_lines(wlog, nlines))
    return out


def make_progress(done: int, total: int, label: str) -> Progress:
    progress = Progress(
        TextColumn(f"{label:<10}"),
        BarColumn(bar_width=None),
        TaskProgressColumn(),
        TextColumn("{task.completed}/{task.total}"),
        expand=True,
    )
    progress.add_task(label, total=max(total, 1), completed=max(0, min(done, max(total, 1))))
    return progress


def build_layout(
    now: str,
    phase: str,
    pid: str,
    alive: str,
    cmd: str,
    log_file: Path,
    meta_file: Path,
    overheat_file: Path,
    metrics: Dict[str, Optional[float]],
    health: Tuple[str, str],
    skips: int,
    fails: int,
    overall_abs: Tuple[int, int],
    random_abs: Tuple[int, int],
    param_abs: Tuple[int, int],
    overall_new: int,
    random_new: int,
    param_new: int,
    pool: List[Tuple[str, int, int, int, int]],
    errors: List[str],
    failed_tail: List[str],
    logs: List[str],
) -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name="top", size=12),
        Layout(name="progress", size=9),
        Layout(name="main", ratio=1),
    )
    layout["main"].split_row(Layout(name="left", ratio=2), Layout(name="right", ratio=3))
    layout["left"].split_column(Layout(name="pool", ratio=1), Layout(name="errors", ratio=1))
    layout["right"].split_column(Layout(name="failed", ratio=2), Layout(name="log", ratio=3))

    header_text = Text()
    header_text.append("Sweep Dashboard\n", style="bold cyan")
    header_text.append(f"time: {now}    phase: {phase}\n")
    header_text.append(f"launcher: {alive} (pid {pid})\n")
    if cmd:
        header_text.append(f"cmd: {cmd[:200]}\n", style="dim")
    header_text.append(f"log: {log_file}\n", style="dim")
    header_text.append(f"meta: {meta_file}", style="dim")
    if overheat_file.exists():
        header_text.append(f"\noverheat: {overheat_file}", style="bold red")
    cpu_text = "n/a" if metrics["cpu_pct"] is None else f"{metrics['cpu_pct']:.1f}%"
    mem_text = (
        "n/a"
        if metrics["mem_pct"] is None
        else f"{metrics['mem_used_gib']:.1f}/{metrics['mem_total_gib']:.1f} GiB ({metrics['mem_pct']:.1f}%)"
    )
    swap_text = f"{metrics['swap_used_gib']:.1f}/{metrics['swap_total_gib']:.1f} GiB ({metrics['swap_pct']:.1f}%)"
    temp_text = "n/a" if metrics["temp_c"] is None else f"{metrics['temp_c']:.1f}C"
    level, reason = health
    health_style = "bold green" if level == "SAFE" else ("bold yellow" if level == "RISKY" else "bold red")
    header_text.append(f"\nCPU: {cpu_text}  MEM: {mem_text}", style="white")
    header_text.append(f"\nSWAP: {swap_text}  TEMP: {temp_text}", style="white")
    header_text.append(f"\nHEALTH: {level} ({reason})", style=health_style)
    layout["top"].update(Panel(header_text, border_style="bright_blue"))

    progress_group = Group(
        make_progress(overall_abs[0], overall_abs[1], "overall"),
        make_progress(random_abs[0], random_abs[1], "random"),
        make_progress(param_abs[0], param_abs[1], "param"),
        Text(
            f"new this run: overall={overall_new}, random={random_new}, param={param_new}    skips={skips}    fails={fails}",
            style="bold white",
        ),
    )
    layout["progress"].update(Panel(progress_group, title="Progress", border_style="green"))

    pool_table = Table(expand=True)
    pool_table.add_column("root", overflow="fold")
    pool_table.add_column("done", justify="right")
    pool_table.add_column("run", justify="right")
    pool_table.add_column("fail", justify="right")
    pool_table.add_column("q", justify="right")
    if not pool:
        pool_table.add_row("(no run root)", "-", "-", "-", "-")
    else:
        for root, d, r, f, q in pool:
            pool_table.add_row(root[-40:], str(d), str(r), str(f), str(q))
    layout["pool"].update(Panel(pool_table, title="Worker Pools", border_style="magenta"))

    err_text = "\n".join(errors) if errors else "(no error lines yet)"
    layout["errors"].update(Panel(err_text, title="Recent Errors", border_style="red"))

    fail_text = "\n".join(failed_tail) if failed_tail else "(no failed worker logs yet)"
    layout["failed"].update(Panel(fail_text, title="Failed Worker Tail", border_style="yellow"))

    log_text = "\n".join(logs) if logs else "(no launcher log yet)"
    layout["log"].update(Panel(log_text, title="Recent Launcher Log", border_style="cyan"))

    return layout


def main() -> int:
    parser = argparse.ArgumentParser(description="Rich monitor for all sweeps")
    parser.add_argument("--root", default=".")
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--tail-lines", type=int, default=20)
    parser.add_argument("--error-lines", type=int, default=12)
    parser.add_argument("--pool-limit", type=int, default=6)
    args = parser.parse_args()

    root = Path(args.root).resolve()
    meta_dir = root / "results" / "_meta"

    meta_link = meta_dir / "run_all_sweeps_latest.meta"
    pid_link = meta_dir / "run_all_sweeps_latest.pid"
    log_link = meta_dir / "run_all_sweeps_latest.log"
    overheat_link = meta_dir / "run_all_sweeps_latest.overheat"
    sampler = SystemSampler()
    sampler.sample()

    if not log_link.exists():
        print(f"log not found: {log_link}")
        return 1

    def render_once() -> Layout:
        meta = parse_kv_file(meta_link)
        log_file = Path(meta.get("log_file", str(log_link)))
        pid_file = Path(meta.get("pid_file", str(pid_link)))
        overheat_file = Path(meta.get("overheat_flag", str(overheat_link)))

        random_total = int(meta.get("random_total", "600"))
        param_total = int(meta.get("param_total", "5670"))
        random_base = int(meta.get("random_base", "0"))
        param_base = int(meta.get("param_base", "0"))

        random_now = count_done(root / "results" / "random_topo")
        param_now = count_done(root / "results") - random_now
        random_done = max(0, random_now - random_base)  # new since this launcher started
        param_done = max(0, param_now - param_base)     # new since this launcher started
        overall_done = random_done + param_done
        overall_total = random_total + param_total
        random_cov = min(random_now, random_total)
        param_cov = min(param_now, param_total)
        overall_cov = min(random_cov + param_cov, overall_total)

        pid, alive, cmd = launcher_state(pid_file)

        recent = tail_lines(log_file, max(args.tail_lines, 400))
        phase = detect_phase(recent)
        pools = pool_rows(parse_run_roots(log_file, args.pool_limit))
        errors = find_error_lines(log_file, args.error_lines)
        failed_tail = failed_worker_tail(log_file)
        logs = recent[-args.tail_lines :]
        metrics = sampler.sample()
        health = evaluate_health(metrics)
        skips = count_log_matches(log_file, r"\[SKIP\]")
        fails = count_log_matches(log_file, r"\[FAIL\]")

        return build_layout(
            now=time.strftime("%F %T %Z"),
            phase=phase,
            pid=pid,
            alive=alive,
            cmd=cmd,
            log_file=log_file,
            meta_file=meta_link,
            overheat_file=overheat_file,
            metrics=metrics,
            health=health,
            skips=skips,
            fails=fails,
            overall_abs=(overall_cov, overall_total),
            random_abs=(random_cov, random_total),
            param_abs=(param_cov, param_total),
            overall_new=overall_done,
            random_new=random_done,
            param_new=param_done,
            pool=pools,
            errors=errors,
            failed_tail=failed_tail,
            logs=logs,
        )

    if args.once:
        from rich.console import Console

        Console().print(render_once())
        return 0

    with Live(render_once(), refresh_per_second=4, screen=True) as live:
        while True:
            live.update(render_once())
            time.sleep(max(args.interval, 0.2))


if __name__ == "__main__":
    raise SystemExit(main())
