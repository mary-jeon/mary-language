#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mary_gate.py — mary-language 윤문 스킬의 결정적 계측 게이트 (SSOT) v2

v2 (2026-08-19): 사용자 지시 — "md에 적어 둔 금지를 py가 실제로 다 잡게. 빡빡하게.
다 읽고 고치게." 그래서 v2는 세는 데서 멈추지 않고, 잡은 자리를 문단 번호와
발췌로 전부 출력한다. exit 1은 '고칠 목록 있음'이라는 뜻이고, 목록을 전수
처치(고치거나 잔존 사유를 문단 원장에 적기)하기 전에는 완료 선언 금지다.

v1 대비 고친 것:
1. 각주: set → Counter 비교. 같은 마커가 2회→1회로 줄어도 exit 2. (v1의 구멍)
2. 부호(— – ·): phrases.md 파싱으로는 죽은 리터럴이 되어 전량 사각이었다.
   코드가 직접 센다.
3. 정정 골격 '아니라': 사용자 확정 기준(기본 전면 제거). 코드 축 + 전수 발췌.
4. 문단 지도 상시 출력: 문단별 글자수·쉼표수. (사용자의 작업 검증 요구)
   450자+ / 문단 쉼표 8+ / 한 문장 쉼표 3+ 는 경고.
5. 지시어(이/그/저) 문단 지도 강화 + 나/내 밀도 지도(정보).
6. 조사류(에서는 등)는 NOISY로 이동 — 평문 한국어가 항상 exit 1이던 문제 제거.
7. --protect "이 책,이 원고": 그 글의 주제어를 지시어·블록리스트 계수에서 제외.

사용:
    python3 mary_gate.py --after 변환본.md [--before 원본.md] [--protect "이 책,이 원고"]

종료 코드:
    0 = 통과
    1 = 고칠 목록 있음 (전수 처치 전 완료 선언 금지)
    2 = 각주 유실/감소 (변환본 채택 금지)
    3 = 판정 불가 (입력 파일 문제)

의존성 없음(표준 라이브러리만). 결정적, LLM 0콜.
"""
import re, sys, os, argparse
from collections import Counter

FOOTNOTE = re.compile(r"\[\^[^\]]+\]")
# 정정 골격. '아니라면/아니라도'(조건·양보)는 제외.
ANIRA = re.compile(r"아니라(?!면|도)")
# 지시어(이/그/저 계열). 예문·인용 속은 사람이 걸러낸다(발췌가 그래서 있다).
PARA_DEMO = re.compile(
    r"그것|이것|저것|그들|그 [가-힣]|저 [가-힣]|이 책|이 문장|이 원고|이 글|이 일|"
    r"이 기술|이 사실|이 대목|이 장|이 구조|이 반복|이 사정")
NAE = re.compile(r"나는|나의|나에게|나를|나도|나만|내가|내 [가-힣]|나 같은")
PARA_DEMO_INFO = 3   # 문단당 이 개수 이상이면 지도에 표시
PARA_DEMO_WARN = 5   # 이 개수 이상이면 경고(exit 1)
PARA_LEN_WARN = 450  # 공백 제외 글자수. 이 이상이면 분할 후보(exit 1)
PARA_COMMA_WARN = 8  # 문단 쉼표 총수 경고선
SENT_COMMA_WARN = 3  # 한 문장 쉼표 경고선 (v1은 4였다)
NAE_INFO = 5         # 문단당 나/내 계열 표시선(정보만, exit에 안 넣음)
MIDDOT_WARN = 5      # ·는 한국어 병기 관행이 있어 이 이상만 경고

# 단어 조각이라 오탐이 잦은 항목: 검출·표시는 하되 exit 판정에는 넣지 않는다.
# v2: 일상 조사(에서는 등)를 추가 — 이것들이 1회 검출로 모든 평문을 경고로 만들던
# v1의 상시 오경보를 없앤다. 판정은 읽고 한다.
NOISY = {"구조", "흐름", "단순한", "신뢰", "기준", "붙는다", "박다",
         "않습니다", "않는다", "않았습니다",
         "에서는", "으로는", "보다는", "쪽으로", "없이",
         "다만", "아마", "어쩌면", "지도 모른다"}
PLACEHOLDER = "~…-XNAB"


def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError as e:
        print(f"[판정불가] 파일을 읽을 수 없다: {path} ({e})")
        sys.exit(3)


def clean_term(piece):
    """블록리스트 한 조각을 대조 가능한 리터럴로 정제. 불가하면 None."""
    t = re.sub(r"\([^)]*\)", "", piece)
    t = re.sub(r'"[^"]*"', "", t)
    t = t.strip().strip("…").strip()
    t = t.lstrip(PLACEHOLDER + " ").rstrip(PLACEHOLDER + " ")
    t = t.strip()
    if len(t) < 2:            # 한 글자(축·결·위)는 오탐 폭발 → 코드로 못 본다. 눈으로.
        return None
    if len(t) > 16 and re.search(r"(나열|설명|반복|붙임|전환|답함|부여|판별|병기)$", t):
        return None
    if "—" in t or "–" in t or "·" in t or "<" in t:
        return None           # 부호 항목은 아래에서 코드가 직접 센다
    return t


def parse_phrases(md_path):
    """phrases.md → [(섹션, [리터럴...]), ...]"""
    out = []
    if not os.path.exists(md_path):
        return out
    for line in open(md_path, encoding="utf-8"):
        s = line.rstrip("\n")
        if s.startswith(">"):
            continue
        m = re.match(r"^#{2,3}\s+(.*)$", s)
        if m:
            sec = re.sub(r"^\d+\.\s*", "", m.group(1)).strip()
            out.append((sec, []))
            continue
        if s.startswith("- ") and out:
            for piece in re.split(r"\s*/\s*|,\s*|\s·\s", s[2:]):
                term = clean_term(piece)
                if term:
                    out[-1][1].append(term)
    return [(sec, list(dict.fromkeys(terms))) for sec, terms in out if terms]


def paragraphs(text):
    body = [p.strip() for p in re.split(r"\n\s*\n", text)
            if p.strip() and not p.strip().startswith("#")]
    return body


def excerpts(paras, pattern, limit=4, width=18):
    """패턴이 걸린 자리를 ¶번호 + 앞뒤 문맥으로 뽑는다. 고치러 갈 수 있게."""
    out = []
    for i, p in enumerate(paras, 1):
        for m in (pattern.finditer(p) if hasattr(pattern, "finditer")
                  else re.finditer(re.escape(pattern), p)):
            a, b = max(0, m.start() - width), min(len(p), m.end() + width)
            frag = p[a:b].replace("\n", " ")
            out.append(f"¶{i}: …{frag}…")
            if len(out) >= limit:
                return out, True
    return out, False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--after", required=True)
    ap.add_argument("--before")
    ap.add_argument("--protect", default="",
                    help='그 글의 주제어. 쉼표 구분 (예: "이 책,이 원고")')
    ap.add_argument("--phrases", default=os.path.join(os.path.dirname(__file__),
                                                      "..", "references", "phrases.md"))
    args = ap.parse_args()

    after = read(args.after)
    paras = paragraphs(after)
    n = len(re.sub(r"\s", "", "".join(paras))) or 1
    protect = [t.strip() for t in args.protect.split(",") if t.strip()]
    exit_code = 0
    triggered = []
    print(f"── mary_gate v2 ── {args.after}  (본문 {n}자, {len(paras)}문단)")
    if protect:
        print(f"   protect: {protect} (지시어·블록리스트 계수에서 제외)")
    print()

    # ── 1) 하드 게이트: 각주 (Counter — 중복 마커 유실도 잡는다)
    if args.before:
        before = read(args.before)
        fb, fa = Counter(FOOTNOTE.findall(before)), Counter(FOOTNOTE.findall(after))
        lost = {k: fb[k] - fa.get(k, 0) for k in fb if fa.get(k, 0) < fb[k]}
        added = {k: fa[k] - fb.get(k, 0) for k in fa if fa[k] > fb.get(k, 0)}
        if lost:
            det = " ".join(f"{k}(-{v})" for k, v in sorted(lost.items()))
            print(f"[실패] 각주 유실/감소: {det}")
            print("       → 변환본 채택 금지. 복구 후 재측정.")
            exit_code = 2
            triggered.append("각주")
        else:
            print(f"[통과] 각주 보존 {sum(fb.values())}회/{len(fb)}종 (등장 횟수까지 일치)")
        if added:
            det = " ".join(f"{k}(+{v})" for k, v in sorted(added.items()))
            print(f"[경고] 원본에 없던 각주 등장: {det}")
            exit_code = max(exit_code, 1)
            triggered.append("각주추가")
        print()
    else:
        print("[안내] --before 없음 → 각주 대조 생략(윤문 시엔 반드시 줄 것)\n")

    # ── 2) 부호 (md 파싱으로는 못 잡아서 코드가 직접 센다)
    em, en, mid = after.count("—"), after.count("–"), after.count("·")
    print(f"부호: — {em}개 / – {en}개 / · {mid}개")
    if em or en:
        for pat, name, c in ((re.compile("—"), "—", em), (re.compile("–"), "–", en)):
            if c:
                exs, _ = excerpts(paras, pat, limit=3)
                for e in exs:
                    print(f"   {name} {e}")
        exit_code = max(exit_code, 1)
        triggered.append("대시")
    if mid >= MIDDOT_WARN:
        print(f"   ⚠ 미들닷 {mid}개 — 병기 관행({MIDDOT_WARN}개 미만)을 넘었다")
        exit_code = max(exit_code, 1)
        triggered.append("미들닷")
    print()

    # ── 3) 정정 골격 '아니라' (사용자 기준: 기본 전면 제거)
    hits = ANIRA.findall(after)
    print(f"정정 골격 '아니라': {len(hits)}회 (아니라면/아니라도 제외)")
    if hits:
        exs, more = excerpts(paras, ANIRA, limit=6)
        for e in exs:
            print(f"   {e}")
        if more:
            print("   …(이하 생략 — 전수는 grep으로)")
        print("   * 기본은 해체: B를 직접 서술. 인용문 속·사실 부정만 사유 적고 잔존.")
        exit_code = max(exit_code, 1)
        triggered.append("아니라")
    print()

    # ── 3-2) 문두 접속부사 (사용자 확정 기준 2026-08-20)
    # 경성(그러나·따라서·또한·그러므로·한편·하지만): 고칠 목록 — 어미로 접거나 삭제.
    # 연성(그리고·그런데·그래서): 밀도만 보고 (말하듯 쓰는 호흡의 일부, 과밀만 경계).
    HARD_CONJ = ["그러나", "따라서", "또한", "그러므로", "한편", "하지만"]
    SOFT_CONJ = ["그리고", "그런데", "그래서"]
    conj_head = lambda w: re.compile(rf"(?:^|[.?!\"”』」]\s*){w}[\s,]", re.M)
    hard_total = 0
    hard_lines = []
    for w in HARD_CONJ:
        pat = conj_head(w)
        n = len(pat.findall(after))
        if n:
            hard_total += n
            hard_lines.append((w, n, pat))
    soft_counts = {w: len(conj_head(w).findall(after)) for w in SOFT_CONJ}
    print(f"문두 접속부사 — 경성 {hard_total}회 / 연성 " +
          " ".join(f"{w} {c}" for w, c in soft_counts.items()))
    if hard_total:
        for w, n, pat in hard_lines:
            print(f"   {w}: {n}회")
            exs, _ = excerpts(paras, pat, limit=3)
            for e in exs:
                print(f"      {e}")
        print("   * 경성 접속부사는 어미(~지만/~니/~고/~는데)로 접거나 지운다. 인용문 내부만 사유 잔존.")
        exit_code = max(exit_code, 1)
        triggered.append("접속부사")
    print()

    # ── 4) phrases.md 전량 대조 (발췌 포함)
    print("═══ phrases.md 블록리스트 전량 대조 ═══")
    total_reliable = 0
    for section, terms in parse_phrases(args.phrases):
        hits = []
        for t in terms:
            if t in protect:
                continue
            c = after.count(t)
            if c > 0:
                hits.append((t, c, t in NOISY or len(t) <= 2))
        if not hits:
            continue
        print(f"\n[{section}]")
        for t, c, noisy in sorted(hits, key=lambda x: -x[1]):
            mark = "  ⚠오탐가능(내용어일 수 있음)" if noisy else ""
            print(f"   {t:<20} {c:>3}회{mark}")
            if not noisy:
                total_reliable += 1
                exit_code = max(exit_code, 1)
                exs, _ = excerpts(paras, re.compile(re.escape(t)), limit=2)
                for e in exs:
                    print(f"      {e}")
    if total_reliable:
        triggered.append("블록리스트")
    print(f"\n확정 검출 항목(오탐 제외): {total_reliable}종\n")

    # ── 5) 문단 지도: 글자수 + 쉼표 (상시 출력 — 작업 검증용)
    print("문단 지도 (글자수·쉼표 — 이 표를 결과 보고에 그대로 쓴다):")
    long_p, heavy_p = [], []
    for i, p in enumerate(paras, 1):
        L = len(re.sub(r"\s", "", p))
        c = p.count(",")
        marks = []
        if L >= PARA_LEN_WARN:
            marks.append(f"⚠길이{L}")
            long_p.append(i)
        if c >= PARA_COMMA_WARN:
            marks.append(f"⚠쉼표{c}")
            heavy_p.append(i)
        print(f"   ¶{i:>2}: {L:>4}자, 쉼표 {c:>2}개  {' '.join(marks)}")
    if long_p:
        exit_code = max(exit_code, 1)
        triggered.append("문단길이")
    if heavy_p:
        exit_code = max(exit_code, 1)
        triggered.append("문단쉼표")
    heavy_s = [s.strip() for s in re.split(r"[.!?…]", after)
               if s.count(",") >= SENT_COMMA_WARN]
    print(f"   한 문장 쉼표 {SENT_COMMA_WARN}개+: {len(heavy_s)}문장")
    for s in heavy_s[:5]:
        print(f"   ⚠ [{s.count(',')}] {s[:44]}…")
    if heavy_s:
        exit_code = max(exit_code, 1)
        triggered.append("문장쉼표")
    print()

    # ── 6) 지시어(이/그/저) 밀도 지도 + 나/내 밀도(정보)
    print(f"지시어 밀도 지도 ({PARA_DEMO_INFO}개+ 표시, {PARA_DEMO_WARN}개+ 경고):")
    shown = False
    for i, p in enumerate(paras, 1):
        q = p
        for t in protect:
            q = q.replace(t, "")
        c = len(PARA_DEMO.findall(q))
        if c >= PARA_DEMO_INFO:
            shown = True
            hot = "  ⚠" if c >= PARA_DEMO_WARN else ""
            if c >= PARA_DEMO_WARN:
                exit_code = max(exit_code, 1)
                if "지시어" not in triggered:
                    triggered.append("지시어")
            print(f"   ¶{i}: {c}개{hot}")
    if not shown:
        print("   없음")
    na_dense = [(i, len(NAE.findall(p))) for i, p in enumerate(paras, 1)]
    na_dense = [(i, c) for i, c in na_dense if c >= NAE_INFO]
    if na_dense:
        print(f"   나/내 계열 {NAE_INFO}개+ 문단(정보): "
              + " ".join(f"¶{i}({c})" for i, c in na_dense))
    print()

    # ── 7) 선언 연쇄: 한 생각을 짧은 선언문 여러 개로 쪼개 착지시키는 버릇
    # ("나는 리모컨이다. 리모컨은 나다. 그러기 위해 나는 눌린다." → 한 문장이면 될 것)
    chains = []
    for i, p in enumerate(paras, 1):
        sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", p) if s.strip()]
        run = []
        for s in sents:
            core = len(re.sub(r"\s", "", s))
            if core <= 24 and s.endswith("다."):
                run.append(s)
            else:
                if len(run) >= 3:
                    chains.append((i, " ".join(run)))
                run = []
        if len(run) >= 3:
            chains.append((i, " ".join(run)))
    print(f"선언 연쇄(짧은 선언문 3연속+): {len(chains)}곳")
    for i, ch in chains[:5]:
        print(f"   ⚠ ¶{i}: {ch[:56]}…")
    if chains:
        exit_code = max(exit_code, 1)
        triggered.append("선언연쇄")
        print("   * 같은 생각이면 한 문장으로 접는다. 재선언·도치 반복 금지.")
    print()

    # ── 8) 삼항 병렬 후보
    tri = []
    for s in re.split(r"[.!?]", after):
        if len(re.findall(r"고,\s", s)) >= 2 \
           or re.search(r"[가-힣]+,\s*[가-힣]+,\s*[가-힣]+", s) and s.count(",") >= 2:
            tri.append(s.strip())
    tri = [t for t in tri if t][:12]
    print(f"삼항 병렬 후보: {len(tri)}개")
    for t in tri[:6]:
        print(f"   ⚠ {t[:52]}…")
    if tri:
        exit_code = max(exit_code, 1)
        triggered.append("삼항")
        print("   * 구체·기능 삼항은 유지, 추상 균형 삼항만 깬다")
    print()

    # ── 판정
    verdict = {0: "통과", 1: "고칠 목록 있음 — 전수 처치 전 완료 선언 금지",
               2: "실패(각주 — 채택 금지)", 3: "판정불가"}[exit_code]
    if triggered:
        print(f"걸린 축: {', '.join(triggered)}")
    print(f"══ 판정: exit {exit_code} = {verdict} ══")
    print("이 수치가 SSOT다. 발췌마다 고치거나, 못 고치면 문단 원장에 잔존 사유를 적는다.")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
