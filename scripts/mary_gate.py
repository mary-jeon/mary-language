#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mary_gate.py — mary-language 윤문 스킬의 결정적 계측 게이트 (SSOT).

이 스크립트의 출력이 진실의 원천이다. 에이전트의 주관 판단·인상으로 덮어쓰지 않는다.
"측정 안 하고 됐다고 함" / "지시어를 조응이라 유지로 합리화" / "각주 하나 빠뜨림" —
이 세 실패를 코드로 막는다.

사용:
    python3 mary_gate.py --after 변환본.md [--before 원본.md]

--before 를 주면 각주 보존을 하드 게이트로 대조한다(윤문에서 가장 흔한 사고).
--before 없이도 변환본의 틱 밀도·문단 지시어 지도·쉼표는 측정한다.

종료 코드:
    0 = 통과 (하드 위반 없음, 밀도 상한 이내)
    1 = 경고 (틱 밀도 상한 초과 또는 4쉼표 문장 존재 — 해당 문단 재작성)
    2 = 실패 (각주 유실 등 하드 위반 — 변환본 채택 금지, 복구 후 재측정)
    3 = 판정 불가 (입력 파일 문제)

의존성 없음(표준 라이브러리만). 결정적, LLM 0콜.
"""
import re, sys, argparse

# ── 틱 밀도: 측정만 한다(SSOT 숫자). exit에 영향 없음 —
#    이 항목들은 내용과 틱이 섞인다(예: '지 않'=주제어 "하지 않겠다", '—'=빈칸 장치 "——").
#    코드가 크러치/내용을 못 가르므로, 숫자만 내고 판정은 에이전트가 읽고 한다. ──
MEASURE = {
    "대조골격(아니라/아니다/기보다/보다는)": r"아니라|아니다|기보다|보다는",
    "em대시(—)":                          r"—",
    "부정회피(지 않)":                      r"지 않",
    "것이다 종결":                          r"것이다",
}
PARA_DEMO_FAIL = 6   # 문단당 이 개수 이상이면 경고(exit 1) — 이 정도면 조응만으론 잘 안 나옴
# ── 지시어(오탐 없는 것만: 주격조사 '이'는 안 셈) ──
DEMONSTRATIVES = {
    "그것/이것":        r"그것|이것",
    "그+명사(조응)":    r"그 [가-힣]",
    "이 책/이 문장류":  r"이 책|이 문장|이 원고|이 글|이 일|이 기술|이 사실|이 대목|이 장",
    "그들":            r"그들",
}
FOOTNOTE = re.compile(r"\[\^[^\]]+\]")
PARA_DEMO = re.compile(r"그것|이것|그들|그 [가-힣]|이 책|이 문장|이 원고|이 글|이 일|이 기술|이 사실|이 대목|이 장")
PARA_DEMO_FLAG = 4   # 문단당 이 개수 이상이면 밀도 지도에 표시

def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError as e:
        print(f"[판정불가] 파일을 읽을 수 없다: {path} ({e})")
        sys.exit(3)

def body_chars(text):
    t = re.sub(r"^#.*$", "", text, flags=re.M)   # 제목 줄 제외
    return len(re.sub(r"\s", "", t))

def paras(text):
    return [p.strip() for p in re.split(r"\n\s*\n", text)
            if p.strip() and not p.strip().startswith("#")]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--after", required=True, help="변환본 .md")
    ap.add_argument("--before", help="원본 .md (각주 보존 대조용)")
    args = ap.parse_args()

    after = read(args.after)
    n = body_chars(after) or 1
    exit_code = 0
    print(f"── mary_gate ── {args.after}  (본문 {n}자)\n")

    # 1) 하드 게이트: 각주 보존 (--before 있을 때)
    if args.before:
        before = read(args.before)
        fb = set(FOOTNOTE.findall(before))
        fa = set(FOOTNOTE.findall(after))
        missing = sorted(fb - fa)
        added = sorted(fa - fb)
        if missing:
            print(f"[실패] 각주 유실 {len(missing)}개: {' '.join(missing)}")
            print("       → 변환본 채택 금지. 해당 위치 복구 후 재측정.")
            exit_code = max(exit_code, 2)
        else:
            print(f"[통과] 각주 보존 {len(fb)}/{len(fb)}")
        if added:
            print(f"[경고] 원본에 없던 각주 {len(added)}개 추가됨: {' '.join(added)}")
            exit_code = max(exit_code, 1)
        print()
    else:
        print("[안내] --before 없음 → 각주 보존 대조 생략(윤문 시엔 주는 것을 권장)\n")

    # 2) 틱 밀도 (측정만 — exit 영향 없음. 에이전트가 읽고 크러치/내용 판정)
    print("틱 밀도 (1,000자당 · SSOT 측정값 · 내용/틱 혼재라 판정은 사람몫):")
    for name, pat in MEASURE.items():
        c = len(re.findall(pat, after))
        print(f"  {name:<28} {c:>3}회  {c*1000/n:>5.2f}/천")
    print()

    # 3) 지시어 구성 (오탐 없는 카운트 — 눈으로 조응/크러치 판정용)
    print("지시어 구성 (그+명사는 대개 조응 — 크러치만 뺄 것):")
    for name, pat in DEMONSTRATIVES.items():
        print(f"  {name:<16} {len(re.findall(pat, after)):>3}")
    print("  * grep '이 [가-힣]' 전체는 주격조사 오탐이므로 세지 않는다")
    print()

    # 4) 쉼표: 문장당 밀도 + 4개+ 문장(하드 아님, 경고)
    sents = re.split(r"[.!?]", after)
    commas = after.count(",")
    ns = max(1, len([s for s in sents if s.strip()]))
    heavy = [s.strip() for s in sents if s.count(",") >= 4]
    print(f"쉼표: 총 {commas}개 / 문장당 {commas/ns:.2f} / 4개+ 문장 {len(heavy)}개")
    for s in heavy:
        print(f"  ⚠️ [{s.count(',')}] {s[:50]}…")
        exit_code = max(exit_code, 1)
    print()

    # 5) 문단 지시어 밀도 지도 (4개+ 문단 = 손볼 후보)
    ps = paras(after)
    dense = [(i, len(PARA_DEMO.findall(p))) for i, p in enumerate(ps, 1)]
    dense = [(i, c) for i, c in dense if c >= PARA_DEMO_FLAG]
    print(f"문단 지시어 밀도 지도 ({PARA_DEMO_FLAG}개+ 문단, {PARA_DEMO_FAIL}개+ = 경고):")
    if dense:
        for i, c in dense:
            hot = "  ⚠️" if c >= PARA_DEMO_FAIL else ""
            if c >= PARA_DEMO_FAIL:
                exit_code = max(exit_code, 1)
            print(f"  ¶{i}: {c}개{hot}")
        print("  * 위 문단을 읽고 순수 크러치만 뺀다(조응·연결어·예문 속 그것은 유지)")
    else:
        print("  없음")
    print()

    verdict = {0: "통과", 1: "경고(재작성 필요)", 2: "실패(채택 금지)", 3: "판정불가"}[exit_code]
    print(f"══ 판정: exit {exit_code} = {verdict} ══")
    print("이 수치가 SSOT다. 결과 보고·완료 선언에는 이 출력값을 그대로 쓴다.")
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
