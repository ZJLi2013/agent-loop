#!/usr/bin/env python3
"""
analyze-results.py — Parse overnight test logs and generate a Markdown report.

Usage:
    python3 scripts/analyze-results.py ./overnight-results/20260330 --output report.md
"""

import argparse
import csv
import os
import re
import sys
from datetime import datetime
from pathlib import Path


def parse_log(log_path: str) -> dict:
    """Extract structured info from a single repo run log."""
    info = {
        "exit_code": None,
        "run_cmd": None,
        "duration_str": None,
        "pytorch_version": None,
        "hip_version": None,
        "errors": [],
        "warnings": [],
        "tail": [],
        "gpu_mem": None,
    }
    if not os.path.isfile(log_path):
        return info

    lines = Path(log_path).read_text(encoding="utf-8", errors="replace").splitlines()

    for line in lines:
        if "EXIT_CODE:" in line:
            m = re.search(r"EXIT_CODE:\s*(\d+)", line)
            if m:
                info["exit_code"] = int(m.group(1))
        if "=== RUN:" in line:
            info["run_cmd"] = line.split("=== RUN:")[-1].strip().rstrip("===").strip()
        if "PyTorch" in line and "HIP:" in line:
            m = re.search(r"PyTorch ([\d.]+\S*),\s*HIP:\s*(\S+)", line)
            if m:
                info["pytorch_version"] = m.group(1)
                info["hip_version"] = m.group(2)
        if re.search(r"\b(error|exception|traceback|failed)\b", line, re.IGNORECASE):
            if len(info["errors"]) < 20:
                info["errors"].append(line.strip())
        if re.search(r"\bwarn(ing)?\b", line, re.IGNORECASE):
            if len(info["warnings"]) < 10:
                info["warnings"].append(line.strip())
        gpu_mem_match = re.search(r"(\d+)\s*MiB\s*/\s*(\d+)\s*MiB", line)
        if gpu_mem_match:
            info["gpu_mem"] = f"{gpu_mem_match.group(1)} / {gpu_mem_match.group(2)} MiB"

    info["tail"] = lines[-30:] if len(lines) >= 30 else lines
    return info


def load_summary(results_dir: str) -> list[dict]:
    """Load summary.csv produced by overnight-runner.sh."""
    csv_path = os.path.join(results_dir, "summary.csv")
    if not os.path.isfile(csv_path):
        print(f"WARN: summary.csv not found in {results_dir}", file=sys.stderr)
        return []
    with open(csv_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def format_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    m, s = divmod(seconds, 60)
    if m < 60:
        return f"{m}m{s}s"
    h, m = divmod(m, 60)
    return f"{h}h{m}m"


def generate_report(results_dir: str) -> str:
    """Build the full Markdown report."""
    rows = load_summary(results_dir)
    today = datetime.now().strftime("%Y-%m-%d")
    parts = [f"# Overnight Test Report — {today}\n"]

    if not rows:
        parts.append("No results found. Check that overnight-runner.sh completed.\n")
        return "\n".join(parts)

    # Summary table
    passed = sum(1 for r in rows if r.get("exit_code") == "0")
    failed = len(rows) - passed
    parts.append(f"**{len(rows)} repos tested** | {passed} passed | {failed} failed\n")
    parts.append("| Repo | Node | Branch | Status | Duration |")
    parts.append("|------|------|--------|--------|----------|")
    for r in rows:
        status = "PASS" if r.get("exit_code") == "0" else f"FAIL (exit={r.get('exit_code')})"
        dur = format_duration(int(r.get("duration_sec", 0)))
        parts.append(f"| {r['repo']} | {r['node']} | {r.get('branch','HEAD')} | {status} | {dur} |")
    parts.append("")

    # Per-repo details
    parts.append("## Per-Repo Details\n")
    for r in rows:
        repo = r["repo"]
        log_file = r.get("log_file", "")
        log_info = parse_log(log_file)

        parts.append(f"### {repo}")
        parts.append(f"- **Node**: {r['node']}")
        parts.append(f"- **Branch**: {r.get('branch', 'HEAD')}")
        parts.append(f"- **Command**: `{log_info['run_cmd'] or 'N/A'}`")
        parts.append(f"- **Exit Code**: {r.get('exit_code')}")
        parts.append(f"- **Duration**: {format_duration(int(r.get('duration_sec', 0)))}")
        if log_info["pytorch_version"]:
            parts.append(f"- **PyTorch**: {log_info['pytorch_version']} (HIP: {log_info['hip_version']})")
        if log_info["gpu_mem"]:
            parts.append(f"- **GPU Memory**: {log_info['gpu_mem']}")

        if log_info["errors"]:
            parts.append("\n**Errors** (top entries):")
            parts.append("```")
            parts.extend(log_info["errors"][:10])
            parts.append("```")

        if log_info["tail"]:
            parts.append("\n<details><summary>Log tail (last 30 lines)</summary>\n")
            parts.append("```")
            parts.extend(log_info["tail"])
            parts.append("```")
            parts.append("</details>")

        parts.append("")

    # AMD GPU notes
    parts.append("## AMD GPU Compatibility Notes\n")
    amd_issues = []
    for r in rows:
        log_info = parse_log(r.get("log_file", ""))
        for e in log_info["errors"]:
            if any(kw in e.lower() for kw in ["hip", "rocm", "hsa", "nccl", "rccl", "gfx"]):
                amd_issues.append(f"- **{r['repo']}**: {e}")
    if amd_issues:
        parts.extend(amd_issues[:20])
    else:
        parts.append("No AMD-specific issues detected.")

    parts.append("\n## Next Steps\n")
    for r in rows:
        if r.get("exit_code") != "0":
            parts.append(f"- [ ] Investigate {r['repo']} failure (exit={r.get('exit_code')})")
    if all(r.get("exit_code") == "0" for r in rows):
        parts.append("- All repos passed. Consider adding more complex test scenarios.")

    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser(description="Analyze overnight test results")
    parser.add_argument("results_dir", help="Path to results directory")
    parser.add_argument("--output", "-o", default=None, help="Output report path (default: stdout)")
    args = parser.parse_args()

    report = generate_report(args.results_dir)

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"Report written to {args.output}")
    else:
        print(report)


if __name__ == "__main__":
    main()
