"""실행 진입점.

    python -m sy_valuation.run
    또는
    python sy_valuation/run.py
"""
import sys
from pathlib import Path

# package 외부에서 실행될 때를 위한 경로 보정
_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from sy_valuation.server import serve

if __name__ == "__main__":
    import argparse, os
    p = argparse.ArgumentParser(description="SY 기업가치평가 시스템 서버")
    p.add_argument("--host", default=os.environ.get("HOST", "0.0.0.0"),
                   help="0.0.0.0=LAN/cloud open, 127.0.0.1=local only")
    p.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8765")),
                   help="default 8765, cloud platforms inject PORT")
    args = p.parse_args()
    serve(args.host, args.port)
