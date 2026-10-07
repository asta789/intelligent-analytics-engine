from __future__ import annotations

import argparse
import json

from app.main import engine


parser = argparse.ArgumentParser(description="Natural-language analytics engine")
parser.add_argument("query", nargs="+", help="Natural language query")
args = parser.parse_args()

print(json.dumps(engine.run(" ".join(args.query)).model_dump(), indent=2, default=str))
