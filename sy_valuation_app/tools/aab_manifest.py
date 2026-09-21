#!/usr/bin/env python3
"""AAB(Android App Bundle) 매니페스트 검증 — bundletool/Java 없이 protobuf 를 직접 파싱.

사용:
  python aab_manifest.py app.aab                       # versionCode/versionName/minSdk/targetSdk 출력
  python aab_manifest.py app.aab --min-target-sdk 36   # targetSdk < 36 이면 exit 1 (Play 정책 검증)
  python aab_manifest.py app.aab --expect-version-code 1012 --expect-version-name 1.0.12

Play Console 은 타겟 API 수준이 정책 기준(2026-08-31 이후 API 36)보다 낮거나, versionCode 가 기존 업로드보다
낮거나 같으면 업로드를 거부한다. CI 에서 이 스크립트로 서명 직후 검증해 잘못된 번들이 releases/ 에 커밋되는 것을 막는다.
표준 라이브러리만 사용.
"""
from __future__ import annotations

import argparse
import sys
import zipfile

MANIFEST = "base/manifest/AndroidManifest.xml"


def _varint(b: bytes, i: int) -> tuple[int, int]:
    r = s = 0
    while True:
        c = b[i]
        i += 1
        r |= (c & 0x7F) << s
        s += 7
        if not c & 0x80:
            return r, i


def _fields(b: bytes):
    """protobuf wire format: yield (field_no, wire_type, value)."""
    i = 0
    while i < len(b):
        key, i = _varint(b, i)
        f, wt = key >> 3, key & 7
        if wt == 0:
            v, i = _varint(b, i)
        elif wt == 1:
            v, i = b[i:i + 8], i + 8
        elif wt == 2:
            ln, i = _varint(b, i)
            v, i = b[i:i + ln], i + ln
        elif wt == 5:
            v, i = b[i:i + 4], i + 4
        else:
            raise ValueError(f"unsupported wire type {wt}")
        yield f, wt, v


def _attrs(element: bytes) -> dict[str, str]:
    """aapt2 XmlElement(field 4 = XmlAttribute{2:name, 3:value, 6:compiled Item{7:Primitive{6|7:int}}})."""
    out: dict[str, str] = {}
    for f, wt, v in _fields(element):
        if f != 4 or wt != 2:
            continue
        name = value = prim = None
        for f2, _, v2 in _fields(v):
            if f2 == 2:
                name = v2.decode()
            elif f2 == 3:
                value = v2.decode(errors="replace")
            elif f2 == 6:
                for f3, _, v3 in _fields(v2):
                    if f3 == 7:
                        for f4, _, v4 in _fields(v3):
                            if f4 in (6, 7):
                                prim = str(v4)
        if name:
            out[name] = value if value else (prim or "")
    return out


def _walk(node: bytes, found: dict[str, dict[str, str]]):
    for f, wt, v in _fields(node):
        if f == 1 and wt == 2:  # XmlElement
            name = None
            children = []
            for f2, _, v2 in _fields(v):
                if f2 == 3:
                    name = v2.decode()
                elif f2 == 5:
                    children.append(v2)
            if name in ("manifest", "uses-sdk"):
                found[name] = _attrs(v)
            for c in children:
                _walk(c, found)


def read_manifest(aab_path: str) -> dict[str, str]:
    with zipfile.ZipFile(aab_path) as z:
        found: dict[str, dict[str, str]] = {}
        _walk(z.read(MANIFEST), found)
    m, sdk = found.get("manifest", {}), found.get("uses-sdk", {})
    return {
        "package": m.get("package", ""),
        "versionCode": m.get("versionCode", ""),
        "versionName": m.get("versionName", ""),
        "compileSdkVersion": m.get("compileSdkVersion", ""),
        "minSdkVersion": sdk.get("minSdkVersion", ""),
        "targetSdkVersion": sdk.get("targetSdkVersion", ""),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("aab")
    ap.add_argument("--min-target-sdk", type=int, help="targetSdkVersion 최소값 (Play 정책)")
    ap.add_argument("--expect-version-code", type=int)
    ap.add_argument("--expect-version-name")
    a = ap.parse_args()

    info = read_manifest(a.aab)
    print(f"AAB: {a.aab}")
    for k, v in info.items():
        print(f"  {k:18s} {v}")

    errors = []
    tsdk = int(info["targetSdkVersion"] or 0)
    if a.min_target_sdk is not None and tsdk < a.min_target_sdk:
        errors.append(f"targetSdkVersion {tsdk} < 요구 {a.min_target_sdk} (Play 정책 미달)")
    if a.expect_version_code is not None and int(info["versionCode"] or 0) != a.expect_version_code:
        errors.append(f"versionCode {info['versionCode']} != 기대 {a.expect_version_code}")
    if a.expect_version_name is not None and info["versionName"] != a.expect_version_name:
        errors.append(f"versionName {info['versionName']} != 기대 {a.expect_version_name}")

    if errors:
        for e in errors:
            print(f"FAIL: {e}")
        return 1
    if a.min_target_sdk is not None or a.expect_version_code is not None or a.expect_version_name is not None:
        print("OK: 검증 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
