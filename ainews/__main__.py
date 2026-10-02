import argparse
import json
import logging
import os

from .pipeline import run


def load_env(path):
    if os.path.exists(path):
        for line in open(path):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def main():
    ap = argparse.ArgumentParser(description="Collect today's most significant AI news into JSON.")
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--env", default=".env")
    ap.add_argument("--dry-run", action="store_true", help="print JSON, don't write files or update dedup memory")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_env(a.env)
    cfg = json.load(open(a.config))
    out = run(cfg, dry_run=a.dry_run)
    if a.dry_run:
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        logging.info("wrote %d items (llm_used=%s)", len(out["items"]), out["llm_used"])


main()
