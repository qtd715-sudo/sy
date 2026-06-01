"""전종목 저평가 스크리너 배치 — CLI 진입점 (GitHub Actions / 수동 실행용).

사용:
    DART_API_KEY=... python -m sy_valuation.build_screener

환경변수:
    DART_API_KEY      DART 인증키 (없으면 Naver 추정으로 빌드 — 정확도 낮음)
    SCREENER_WORKERS  병렬 워커 수 (기본 12)
    SCREENER_LIMIT    테스트용 — 앞 N개만 평가

결과: data/screener_cache.json (GitHub Actions 가 커밋 → Render 가 서빙).
회사망에서 DART 가 막히므로, 실제 정확평가는 GitHub Actions(클린 네트워크)에서 수행한다.
"""

from __future__ import annotations

import logging
import os


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    from .server import App

    app = App()
    if not app.dart.enabled:
        print("[!] DART_API_KEY 미설정 - Naver 추정 데이터로 빌드 (적정가 정확도 낮음).")
    else:
        print("[OK] DART 연동 - 실제 재무로 평가.")

    workers = int(os.environ.get("SCREENER_WORKERS", "12"))
    limit_env = os.environ.get("SCREENER_LIMIT")
    limit = int(limit_env) if limit_env else None

    summary = app.build_full_screener(limit=limit, max_workers=workers)
    print("완료:", summary)


if __name__ == "__main__":
    main()
