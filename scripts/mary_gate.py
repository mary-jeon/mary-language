#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mary_gate.py — mary-language 윤문 스킬의 결정적 계측 게이트 (SSOT).

이 스크립트의 출력이 진실의 원천이다. 에이전트의 주관 판단·인상으로 덮어쓰지 않는다.

핵심 설계: **게이트는 phrases.md를 직접 읽어 그 안의 모든 항목을 원문에 대조한다.**
→ .py와 .md가 영구히 일치한다. phrases.md에 표현을 추가하면 게이트가 자동으로 다 잡는다.
이것이 "닷엠디처럼 모든 걸 걸러라"의 구현이다. (SKILL.md·phrases.md ↔ 이 코드가 한 몸)

막는 3대 실패:
1. 측정 안 하고 "됐다" — 모든 항목을 실제로 세서 숫자로 낸다.
2. 각주 하나 빠뜨림 — 원본 대비 각주 유실을 하드 게이트(exit 2)로 잡는다.
3. .md엔 있는데 .py가 안 보는 항목 — phrases.md 전량을 대조해 사각을 없앤다.

사용:
    python3 mary_gate.py --after 변환본.md [--before 원본.md]

종료 코드:
    0 = 통과 (하드 위반 없음 + 블록리스트 확정 항목 0)
    1 = 경고 (블록리스트 항목 검출 / 4쉼표 문장 / 문단 지시어 밀집 / 삼항 후보)
    2 = 실패 (각주 유실 등 하드 위반 — 변환본 채택 금지)
    3 = 판정 불가 (입력 파일 문제)

의존성 없음(표준 라이브러리만). 결정적, LLM 0콜.
"""
import re, sys, os, argparse

FOOTNOTE = re.compile(r"\[\^[^\]]+\]")
PARA_DEMO = re.compile(r"그것|이것|그들|그 [가-힣]|이 책|이 문장|이 원고|이 글|이 일|이 기술|이 사실|이 대목|이 장")
PARA_DEMO_INFO = 4   # 문단당 이 개수 이상이면 지도에 표시
PARA_DEMO_WARN = 6   # 이 개수 이상이면 경고(exit 1)

# 단어 조각이라 오탐이 잦은 항목(예: 축=압축, 결=결국/연결). 검출은 하되 ⚠로 표시하고
# exit 판정에는 넣지 않는다 — 판정은 사람이 눈으로.
NOISY = {"축", "결", "결이", "구조", "흐름", "단순한", "신뢰", "기준",
         "붙는다", "박다", "않습니다", "않는다", "위", "축, 결"}
# 이 책의 주제어라 내용일 수 있는 것(윤문 대상 글에 따라 다름 — 참고용 주석만)
PLACEHOLDER = "~…-XNAB"

def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError as e:
        print(f"[판정불가] 파일을 읽을 수 없다: {path} ({e})")
        sys.exit(3)

def clean_term(piece):
    """블록리스트 한 조각을 grep 가능한 리터럴로 정제. 불가하면 None."""
    t = re.sub(r"\([^)]*\)", "", piece)          # 괄호 설명 제거
    t = re.sub(r'"[^"]*"', "", t)                # 예시 인용 제거
    t = t.strip().strip("…").strip()
    t = t.lstrip(PLACEHOLDER + " ").rstrip(PLACEHOLDER + " ")
    t = t.strip()
    if len(t) < 2:                               # 너무 짧으면(한 글자) 오탐 폭발 → 스킵
        return None
    # 서술형 문장(설명)인지 대략 판별: 너무 길고 서술 동사로 끝나면 스킵
    if len(t) > 16 and re.search(r"(나열|설명|반복|붙임|전환|답함|부여|판별)$", t):
        return None
    return t

def parse_phrases(md_path):
    """phrases.md → [(섹션, [리터럴 term...]), ...]. 블록리스트를 코드로 로드."""
    out = []
    if not os.path.exists(md_path):
        return out
    section = None
    for line in open(md_path, encoding="utf-8"):
        s = line.rstrip("\n")
        if s.startswith(">"):                    # 블록쿼트(처리규칙) 스킵
            continue
        m = re.match(r"^#{2,3}\s+(.*)$", s)
        if m:
            section = re.sub(r"^\d+\.\s*", "", m.group(1)).strip()
            out.append((section, []))
            continue
        if s.startswith("- ") and out:
            body = s[2:]
            for piece in re.split(r"\s*/\s*|,\s*|\s·\s", body):
                term = clean_term(piece)
                if term:
                    out[-1][1].append(term)
    # 섹션 중복 term 정리
    return [(sec, list(dict.fromkeys(terms))) for sec, terms in out if terms]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--after", required=True)
    ap.add_argument("--before")
    ap.add_argument("--phrases", default=os.path.join(os.path.dirname(__file__),
                                                      "..", "references", "phrases.md"))
    args = ap.parse_args()

    after = read(args.after)
    body = re.sub(r"^#.*$", "", after, flags=re.M)
    n = len(re.sub(r"\s", "", body)) or 1
    exit_code = 0
    print(f"── mary_gate ── {args.after}  (본문 {n}자)")
    print("   게이트는 phrases.md를 읽어 전량 대조한다 (.py ↔ .md 한 몸)\n")

    # 1) 하드 게이트: 각주 보존
    if args.before:
        before = read(args.before)
        fb, fa = set(FOOTNOTE.findall(before)), set(FOOTNOTE.findall(after))
        missing, added = sorted(fb - fa), sorted(fa - fb)
        if missing:
            print(f"[실패] 각주 유실 {len(missing)}개: {' '.join(missing)}")
            print("       → 변환본 채택 금지. 복구 후 재측정.")
            exit_code = max(exit_code, 2)
        else:
            print(f"[통과] 각주 보존 {len(fb)}/{len(fb)}")
        if added:
            print(f"[경고] 원본에 없던 각주 {len(added)}개: {' '.join(added)}")
            exit_code = max(exit_code, 1)
        print()
    else:
        print("[안내] --before 없음 → 각주 보존 대조 생략(윤문 시엔 주는 것을 권장)\n")

    # 2) phrases.md 전량 대조 (핵심)
    print("═══ phrases.md 블록리스트 전량 대조 ═══")
    total_reliable = 0
    for section, terms in parse_phrases(args.phrases):
        hits = []
        for t in terms:
            c = after.count(t)
            if c > 0:
                hits.append((t, c, t in NOISY or len(t) <= 2))
        if not hits:
            continue
        print(f"\n[{section}]")
        for t, c, noisy in sorted(hits, key=lambda x: -x[1]):
            mark = "  ⚠오탐가능(내용어일 수 있음)" if noisy else ""
            if not noisy:
                total_reliable += 1
                exit_code = max(exit_code, 1)
            print(f"   {t:<22} {c:>3}회{mark}")
    print(f"\n확정 검출 항목(오탐 제외): {total_reliable}종\n")

    # 3) 삼항 병렬(tricolon) 후보 — 구조 틱, 코드가 잡는다
    tri = []
    for s in re.split(r"[.!?]", after):
        if len(re.findall(r"고,\s", s)) >= 2 or len(re.findall(r"도\s+[가-힣]+도", s)) >= 1 \
           or len(re.findall(r"[가-힣]+,\s*[가-힣]+,\s*[가-힣]+", s)) >= 1 and s.count(",") >= 2:
            tri.append(s.strip())
    tri = [t for t in tri if t][:12]
    print(f"삼항 병렬(tricolon) 후보: {len(tri)}개")
    for t in tri[:6]:
        print(f"   ⚠ {t[:52]}…")
        exit_code = max(exit_code, 1)
    if tri:
        print("   * 구체·기능(3연산)·주제 삼항은 유지, 추상 균형 삼항만 깬다")
    print()

    # 4) 쉼표: 4개+ 문장
    sents = re.split(r"[.!?]", after)
    heavy = [s.strip() for s in sents if s.count(",") >= 4]
    print(f"쉼표: 총 {after.count(',')}개 / 4개+ 문장 {len(heavy)}개")
    for s in heavy:
        print(f"   ⚠ [{s.count(',')}] {s[:48]}…")
        exit_code = max(exit_code, 1)
    print()

    # 5) 문단 지시어 밀도 지도
    ps = [p.strip() for p in re.split(r"\n\s*\n", after)
          if p.strip() and not p.strip().startswith("#")]
    dense = [(i, len(PARA_DEMO.findall(p))) for i, p in enumerate(ps, 1)]
    dense = [(i, c) for i, c in dense if c >= PARA_DEMO_INFO]
    print(f"문단 지시어 밀도 지도 ({PARA_DEMO_INFO}개+ 표시, {PARA_DEMO_WARN}개+ 경고):")
    if dense:
        for i, c in dense:
            hot = "  ⚠" if c >= PARA_DEMO_WARN else ""
            if c >= PARA_DEMO_WARN:
                exit_code = max(exit_code, 1)
            print(f"   ¶{i}: {c}개{hot}")
        print("   * 순수 크러치만 뺀다(조응·연결어·예문 속 그것은 유지)")
    else:
        print("   없음")
    print()

    verdict = {0: "통과", 1: "경고(검출 항목 있음 — 읽고 판정)", 2: "실패(채택 금지)", 3: "판정불가"}[exit_code]
    print(f"══ 판정: exit {exit_code} = {verdict} ══")
    print("이 수치가 SSOT다. ⚠오탐가능·삼항·지시어는 내용/틱이 섞이니 읽고 판정하되,")
    print("각주 유실(exit 2)만은 코드가 완벽히 막는다. 결과 보고엔 이 출력값을 그대로 쓴다.")
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
