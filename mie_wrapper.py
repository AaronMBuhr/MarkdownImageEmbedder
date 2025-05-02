#!/usr/bin/env python3
"""
Markdown‑Image‑Embedder wrapper

• Supports wild‑cards on Windows (glob)
• Handles filenames with spaces, ampersands, Unicode, …
• Creates *.bak backups before touching originals
• Streams each file through markdown_image_embedder.py, collecting a master log
• Pops the master log into VS Code via pipe‑to-code.bat
"""

from __future__ import annotations
import argparse, glob, os, shutil, subprocess, sys, tempfile, textwrap
from pathlib import Path
import time
from typing import List

# ────────────────────────────────────────────────  constants
EMBEDDER = Path(r"E:\source\mine\MarkdownImageEmbedder\markdown_image_embedder.py")
PIPE_TO_CODE = Path(r"C:\utils\winutils\pipe-to-code.bat")      # ← existing helper
CONDA_ENV = "mypython312"

# ────────────────────────────────────────────────  helpers
def fail(msg: str, code: int = 1) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)

def good_env() -> bool:
    return os.environ.get("CONDA_DEFAULT_ENV") == CONDA_ENV

def run_embedder(
    infile: Path,
    outfile: Path,
    args_from_cli: argparse.Namespace,
    log: Path,
) -> bool:
    """Return True on success."""
    cmd: List[str] = [
        sys.executable, str(EMBEDDER),
        "--input-file", str(infile),
        "--output-file", str(outfile),
        "--log-file", str(log),
        "--quiet",          # silence embedder console
        "--verbose",        # …but write INFO+ to log file
    ]
    # user‑controlled extras
    if args_from_cli.debug:
        cmd.append("--debug")           # overrides quiet/verbose if they want
    if args_from_cli.yarle:
        cmd.append("--yarle")
    if args_from_cli.quality:
        cmd += ["--quality", str(args_from_cli.quality)]
    if args_from_cli.max_size:
        cmd += ["--max-size", str(args_from_cli.max_size)]
    if args_from_cli.max_width:
        cmd += ["--max-width", str(args_from_cli.max_width)]
    if args_from_cli.max_height:
        cmd += ["--max-height", str(args_from_cli.max_height)]

    proc = subprocess.run(cmd, text=True)
    return proc.returncode == 0

# ───────────────────────────── helper to open the log in VS Code
def open_log_in_vscode(log_path: Path) -> None:
    """
    Try pipe-to-code.bat first (so the temp log self‑deletes);
    if that fails, fall back to launching VS Code directly.
    """
    def file_exists(p: Path) -> bool:
        return p.is_file()

    # 1) pipe‑to‑code route
    if file_exists(PIPE_TO_CODE):
        proc = subprocess.Popen(
            ["cmd.exe", "/c", str(PIPE_TO_CODE), "-continue", str(log_path)],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        # give it a moment – if it exits in <0.5 s it almost certainly failed
        time.sleep(0.5)
        if proc.poll() is None:    # still running → good
            return
        # otherwise fall through to direct Code launch

    # 2) direct VS Code route
    # try the standard 'code' on PATH first
    for code_cmd in ("code", r"C:\Program Files\Microsoft VS Code\Code.exe"):
        try:
            subprocess.Popen([code_cmd, "-n", str(log_path)])
            return
        except FileNotFoundError:
            continue

    print("WARNING: could not launch VS Code – see log file at:", log_path, file=sys.stderr)

# ────────────────────────────────────────────────  main
def main() -> int:
    if not good_env():
        fail(
            textwrap.dedent(f"""
            Conda environment “{CONDA_ENV}” is not active.
            Activate it first:  conda activate {CONDA_ENV}
            """)
        )

    ap = argparse.ArgumentParser(
        description="Wrapper around markdown_image_embedder.py (wildcards, logs, backups).",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    ap.add_argument("pattern", nargs="+", help="File or wildcard pattern(s) to process")
    ap.add_argument("-q","--quality", type=int, choices=range(1,10), default=5)
    ap.add_argument("-y","--yarle", action="store_true")
    ap.add_argument("-m","--max-size", type=int, default=10, metavar="MB")
    ap.add_argument("-W","--max-width", type=int)
    ap.add_argument("-H","--max-height", type=int)
    ap.add_argument("-d","--debug", action="store_true")
    ap.add_argument("-v","--verbose", action="store_true")
    args = ap.parse_args()

    # Resolve all files (Windows shell does NOT expand globs)
    files: List[Path] = []
    for patt in args.pattern:
        matched = [Path(p) for p in glob.glob(patt, recursive=False)]
        if not matched:
            print(f"No matches for pattern: {patt}")
        files.extend(matched)
    if not files:
        fail("Nothing to do.")

    master_log = Path(tempfile.gettempdir()) / f"mie_master_{os.getpid()}.log"
    with master_log.open("w", encoding="utf-8") as mlog:
        mlog.write("=== Markdown‑Image‑Embedder batch run ===\n")
        mlog.write(f"Files: {len(files)}\n\n")

    ok = 0
    for f in files:
        if not f.exists():
            print(f"Skip missing file: {f}")
            continue

        bak = f.with_suffix(f.suffix + ".bak")
        try:
            shutil.copy2(f, bak)
        except Exception as e:
            print(f"Backup failed for {f}: {e}")
            continue

        fd, tmpname = tempfile.mkstemp(prefix="mie_", suffix=".log")
        os.close(fd)                           # ← close the handle so Windows can delete later
        file_log = Path(tmpname)
        success = run_embedder(bak, f, args, file_log)

        with master_log.open("a", encoding="utf-8") as mlog, file_log.open(encoding="utf-8") as flog:
            mlog.write(f"\n--- {f} ---\n")
            mlog.writelines(flog.readlines())

        file_log.unlink(missing_ok=True)
        if success:
            ok += 1
            print(f"✓ {f}")
        else:
            print(f"✗ {f} (see log)")

    with master_log.open("a", encoding="utf-8") as mlog:
        mlog.write(f"\n=== Summary: {ok}/{len(files)} OK ===\n")

    # Fire up VS Code view of the log without blocking this process
    print("Opening master log in VS Code …")
    #subprocess.Popen(
    #    ["cmd.exe", "/c", str(PIPE_TO_CODE), "-continue", str(master_log)],
    #    creationflags=subprocess.CREATE_NO_WINDOW,
    #)
    open_log_in_vscode(master_log)


    return 0 if ok == len(files) else 1

if __name__ == "__main__":
    sys.exit(main())

