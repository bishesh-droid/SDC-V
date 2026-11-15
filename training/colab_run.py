"""One command for the whole Colab job. Run it from a notebook cell after mounting Drive:

    from google.colab import drive; drive.mount("/content/drive")
    !python /content/drive/MyDrive/SDC-V/training/colab_run.py

Stages, in order (each is skipped when its marker file exists in <drive>/training/outputs, so a rerun after a disconnect continues):
    setup      copy the project from Drive to fast local disk, link outputs back to Drive, install libraries, build data if missing
    zeroshot   untrained Qwen on 50 rows per split            -> scores_zeroshot.txt
    smoke      20 training steps on 200 rows (catches version errors in minutes)
    train      full QLoRA run, checkpoints every 50 steps; resumes from the newest one; then answers all test rows
    score      scores the fine-tuned predictions               -> scores_finetuned.txt
    benchmark  hand-written chat cases through the real pipeline with the adapter -> benchmark_local.txt, intake_compare_local.json

Everything written to Drive: outputs/intake-lora/final (adapter), pred_*.jsonl, scores_*.txt, logs/*.log, checkpoints.
Options:  --drive PATH  --skip-smoke  --skip-zeroshot  --force (ignore markers)  --model NAME
Stops at the first failing stage and prints the end of its log: paste that to get it fixed.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

WORK = Path("/content/sdcv")
IGNORE = shutil.ignore_patterns(".venv", "node_modules", ".git", "__pycache__", "*.pyc", "outputs", "*.db", "*.zip")


def run(cmd: list[str], log: Path, cwd: Path) -> int:
    """Stream a command to the screen and to a log file on Drive."""
    log.parent.mkdir(parents=True, exist_ok=True)
    print(f"\n$ {' '.join(cmd)}\n  (log: {log})", flush=True)
    with log.open("a", encoding="utf-8") as f:
        p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        for line in p.stdout:
            sys.stdout.write(line); f.write(line)
        return p.wait()


def fail(stage: str, log: Path) -> None:
    tail = "\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-40:]) if log.exists() else ""
    print(f"\n=== stage '{stage}' FAILED. Last lines of {log}:\n{tail}\n\nPaste this to get it fixed, then rerun the same command.")
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--drive", default="/content/drive/MyDrive/SDC-V")
    ap.add_argument("--model", default="Qwen/Qwen2.5-3B-Instruct")
    ap.add_argument("--name", default="intake-lora-v2", help="adapter folder name; v1 (intake-lora) is kept untouched")
    ap.add_argument("--skip-smoke", action="store_true")
    ap.add_argument("--skip-zeroshot", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    drive = Path(a.drive)
    if not (drive / "training" / "train_intake_qlora.py").exists():
        sys.exit(f"{drive}/training/train_intake_qlora.py not found. Upload the SDC-V folder to Drive, or pass --drive PATH.")
    out = drive / "training" / "outputs"
    out.mkdir(parents=True, exist_ok=True)
    logs = out / "logs"
    py = sys.executable

    # ---- setup (always runs: local disk is wiped between sessions)
    print("== setup")
    try:   # a dropped Drive mount shows up as "Transport endpoint is not connected" and makes every path look missing
        list((drive / "training").iterdir())
    except OSError as e:
        sys.exit(f"Google Drive is not readable ({e}).\nRuntime > Restart session, run the mount cell again (Allow), then rerun this cell.")
    if WORK.exists():
        shutil.rmtree(WORK, ignore_errors=True)
    for part in ("backend/app", "benchmark", "training"):      # only what the job needs: never .env, never other folders
        try:
            shutil.copytree(drive / part, WORK / part, ignore=IGNORE)
        except (OSError, shutil.Error) as e:
            sys.exit(f"Copying {part} from Drive failed: {e}\nIf it says 'Transport endpoint is not connected', restart the session, "
                     "remount Drive and rerun.")
    tdir = WORK / "training"
    (tdir / "outputs").symlink_to(out, target_is_directory=True)     # checkpoints and results land on Drive
    if subprocess.call([py, "-c", "import torch; assert torch.cuda.is_available()"]) != 0:
        sys.exit("No GPU. Runtime > Change runtime type > T4 GPU, then rerun.")
    rc = run([py, "-m", "pip", "install", "-q", "transformers>=4.46", "trl>=0.12", "peft>=0.13", "bitsandbytes",
              "accelerate", "datasets", "pydantic"], logs / "setup.log", tdir)
    if rc:
        fail("setup", logs / "setup.log")
    # Colab ships a torchao that peft/transformers reject at import time; we do not use it
    subprocess.call([py, "-m", "pip", "uninstall", "-y", "-q", "torchao"])
    if True:   # always rebuild: deterministic, and the copy on Drive may predate a generator change
        if run([py, "make_intake_dataset.py"], logs / "setup.log", tdir):
            fail("setup", logs / "setup.log")

    def stage(name: str, cmd: list[str], skip: bool = False) -> bool:
        marker = out / f".done_{name}"
        if skip or (marker.exists() and not a.force):
            print(f"\n== {name}: skipped ({'by flag' if skip else 'already done'})")
            return False
        print(f"\n== {name}")
        if run(cmd, logs / f"{name}.log", tdir):
            fail(name, logs / f"{name}.log")
        marker.write_text("ok\n")
        return True

    def capture(cmd_list: list[list[str]], dest: Path, log: Path) -> None:
        dest.write_text("", encoding="utf-8")
        for c in cmd_list:
            tmp = log.with_suffix(".tmp")
            tmp.unlink(missing_ok=True)
            if run(c, tmp, tdir):
                fail("score", tmp)
            dest.write_text(dest.read_text(encoding="utf-8") + tmp.read_text(encoding="utf-8"), encoding="utf-8")

    # ---- zero-shot (an earlier run that scored 0 rows is not a result: redo it)
    zs = out / "scores_zeroshot.txt"
    if zs.exists() and "(0 rows scored" in zs.read_text(encoding="utf-8"):
        (out / ".done_zeroshot").unlink(missing_ok=True)
    if stage("zeroshot", [py, "-W", "ignore", "intake_eval.py", "--backend", "local", "--model", a.model, "--limit", "50"],
             skip=a.skip_zeroshot):
        text = (logs / "zeroshot.log").read_text(encoding="utf-8", errors="replace")
        (out / "scores_zeroshot.txt").write_text("\n".join(l for l in text.splitlines() if "api errors" not in l) + "\n", encoding="utf-8")

    # ---- smoke test
    stage("smoke", [py, "train_intake_qlora.py", "--model", a.model, "--fp16", "--max_steps", "20", "--train_rows", "200",
                    "--name", "smoke"], skip=a.skip_smoke)

    # ---- full training + predictions
    stage(f"train_{a.name}", [py, "train_intake_qlora.py", "--model", a.model, "--fp16", "--predict", "--resume", "--name", a.name])

    # ---- score the fine-tuned predictions
    marker = out / f".done_score_{a.name}"
    if marker.exists() and not a.force:
        print("\n== score: skipped (already done)")
    else:
        print("\n== score")
        cmds = [[py, "-W", "ignore", "intake_eval.py", "--backend", "file", "--split", s, "--predictions",
                 str(out / a.name / f"pred_{s}.jsonl")] for s in ("test_iid", "test_heldout", "test_ood", "test_sparse")]
        capture(cmds, out / f"scores_{a.name}.txt", logs / "score.log")
        marker.write_text("ok\n")

    # a benchmark where cases errored (model never ran) is not a result: redo it
    cj = out / f"intake_compare_{a.name}.json"
    if cj.exists() and '"status": "error"' in cj.read_text(encoding="utf-8"):
        (out / f".done_benchmark_{a.name}").unlink(missing_ok=True)

    # ---- hand-written cases through the real pipeline with the fine-tuned adapter (the test that is not synthetic)
    if stage(f"benchmark_{a.name}", [py, "-W", "ignore", str(WORK / "benchmark" / "run_intake_compare.py"), "--backend", "local",
                           "--adapter", str(out / a.name / "final"), "--out", str(out / f"intake_compare_{a.name}.json")]):
        text = (logs / f"benchmark_{a.name}.log").read_text(encoding="utf-8", errors="replace")
        (out / f"benchmark_{a.name}.txt").write_text("\n".join(l for l in text.splitlines() if "Loading weights" not in l and not l.startswith("  ") or l.startswith("  FAIL")) + "\n", encoding="utf-8")

    for name in (f"scores_{a.name}.txt", f"benchmark_{a.name}.txt"):
        f = out / name
        if f.exists():
            print(f"\n######## {name}\n{f.read_text(encoding='utf-8')}")
    print("\nDONE. Adapter: ", out / a.name / "final")
    print("Copy it to your laptop and set SDCV_INTAKE_BACKEND=local SDCV_LOCAL_ADAPTER=<that folder>.")


if __name__ == "__main__":
    main()
