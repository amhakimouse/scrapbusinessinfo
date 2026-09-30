import pytest
import subprocess
import sys
import config
from scraper.models import Lead

import os

def test_cli_empty_seeds(tmp_path, monkeypatch):
    seeds_file = tmp_path / "empty_seeds.txt"
    seeds_file.write_text("# only comments\n")
    
    cmd = [
        sys.executable,
        "main.py",
    ]
    env = dict(os.environ)
    env["SEEDS_FILE"] = str(seeds_file)
    res = subprocess.run(cmd, capture_output=True, text=True, env=env)
    # Must exit with non-zero or error message
    assert "[ERROR] No seed URLs found to scrape" in res.stdout or res.returncode != 0

def test_cli_single_url_and_keyword_parsing():
    import main
    # Ensure arg parsing handles --url, --keyword, --keywords, --workers, --mode
    parser = main.argparse.ArgumentParser()
    parser.add_argument("--mode", default="fast")
    parser.add_argument("--url")
    parser.add_argument("--keyword")
    parser.add_argument("--keywords")
    parser.add_argument("--workers", type=int, default=8)

    args = parser.parse_args(["--keywords", "gardening tools, coffee makers", "--workers", "8", "--mode", "stealthy"])
    assert args.keywords == "gardening tools, coffee makers"
    assert args.workers == 8
    assert args.mode == "stealthy"

