#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mary_gate.py — mary-language 윤문 스킬의 결정적 계측 게이트 (SSOT) v3

v3 (2026-09-02): 게이트를 세 층으로 나눈다. 사람 글도 늘 exit 1이 나던 v2를 고친 것.

  exit 2  하드 위반 — 변환본 채택 금지
          각주 유실 · 숫자 유실 · 직접 인용 변형  (원본↔변환본 대조, 코드가 완전히 판정)
  exit 1  고칠 목록 — 사용자가 확정한 금지 문형만
          대시(— –) · '아니라' 정정 골격 · 문두 경성 접속부사 · 블록리스트 [게이트] 섹션
          (강조어·가짜 강조·메타 선언) · 450자+ 문단 · 지시어 5개+ 문단 · 선언 연쇄(재선언)
          · 영문 용어 유실 · 원본에 없던 각주
  exit 0  통과 — 아래 참고 정보는 exit에 영향 없음
          미들닷 · 블록리스트 나머지 섹션 · 삼항 후보 · 쉼표 지도 · 나/내 밀도 · 지시어 3~4개

v2 대비 고친 것:
1. Windows 한글 콘솔(cp949)에서 첫 출력 줄에서 죽던 문제 — stdout을 UTF-8로 고정.
2. 숫자·직접 인용 보존을 각주와 같은 방식(Counter 대조)으로 하드 게이트에 추가.
   SKILL 2단계의 "protected span"을 코드가 실제로 대조한다.
3. 블록리스트는 phrases.md 섹션 제목의 태그로 층을 정한다 — [게이트]는 exit 1,
   [설명]은 파싱 제외, 태그 없음은 정보. 설명문이 잘려 금지어가 되던 사고("위에서",
   "문자 그대로의" 등)를 없앤다.
4. 선언 연쇄는 "짧은 문장 3연속"이 아니라 "인접 문장이 같은 내용어를 재선언"할 때만.
   ("밥은 없고 라면은 있었다" 같은 사람 문장이 걸리지 않는다.)
5. 삼항 후보·쉼표는 정보로 내린다. 판정은 사람이 읽고 한다.

사용:
    python mary_gate.py --after 변환본.md --before 원본.md [--protect "이 책,이 원고"]

종료 코드:
    0 = 통과
    1 = 고칠 목록 있음 (전수 처치 전 완료 선언 금지)
    2 = 하드 위반 — 각주·숫자·인용 (변환본 채택 금지)
    3 = 판정 불가 (입력 파일 문제)

의존성 없음(표준 라이브러리만). 결정적, LLM 0콜.
"""
import re, sys, os, argparse
from collections import Counter

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass

FOOTNOTE = re.compile(r"\[\^[^\]]+\]")
NUMBER = re.compile(r"\d+(?:[.,:/]\d+)*")
LATIN = re.compile(r"[A-Za-z][A-Za-z0-9_.+-]{1,}")
QUOTE = re.compile(r"[“\"「『]([^”\"」』\n]{4,})[”\"」』]")
# 정정 골격. '아니라면/아니라도'(조건·양보)는 제외.
ANIRA = re.compile(r"아니라(?!면|도)")
# 지시어(이/그/저 계열). 예문·인용 속은 사람이 걸러낸다(발췌가 그래서 있다).
PARA_DEMO = re.compile(
    r"그것|이것|저것|그들|그 [가-힣]|저 [가-힣]|이 책|이 문장|이 원고|이 글|이 일|"
    r"이 기술|이 사실|이 대목|이 장|이 구조|이 반복|이 사정")
NAE = re.compile(r"나는|나의|나에게|나를|나도|나만|내가|내 [가-힣]|나 같은")
HARD_CONJ = ["그러나", "따라서", "또한", "그러므로", "한편", "하지만"]
SOFT_CONJ = ["그리고", "그런데", "그래서"]
SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
# 재선언 판정에서 무시할 조사·어미
STRIP_SUFFIX = re.compile(
    r"(이다|였다|한다|있다|없다|된다|는다|았다|었다|겠다|이며|이고|에서|으로|"
    r"은|는|이|가|을|를|의|도|로|에|과|와)$")

PARA_DEMO_INFO = 3   # 문단당 이 개수 이상이면 지도에 표시
PARA_DEMO_WARN = 5   # 이 개수 이상이면 고칠 목록(exit 1)
PARA_LEN_WARN = 450  # 공백 제외 글자수. 이 이상이면 분할(exit 1) — 사용자 확정 기준 5
PARA_COMMA_INFO = 8  # 문단 쉼표 총수 표시선(정보)
SENT_COMMA_INFO = 3  # 한 문장 쉼표 표시선(정보)
NAE_INFO = 5         # 문단당 나/내 계열 표시선(정보)
MIDDOT_INFO = 5      # ·는 한국어 병기 관행이 있어 이 이상만 표시(정보)
SHORT_SENT = 24      # 선언 연쇄 후보 문장의 공백 제외 길이 상한

# 단어 조각이라 오탐이 잦은 항목: 검출·표시는 하되 판정에는 넣지 않는다.
NOISY = {"구조", "흐름", "단순한", "신뢰", "기준", "붙는다", "박다",
         "않습니다", "않는다", "않았습니다",
         "에서는", "으로는", "보다는", "쪽으로", "없이"}
PLACEHOLDER = "~…-XNAB"
GATE_TAG, SKIP_TAG = "[게이트]", "[설명]"


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
        return None           # 부호 항목은 코드가 직접 센다
    return t


def parse_phrases(md_path):
    """phrases.md → [(섹션, [리터럴...], gate:bool), ...]

    섹션 제목의 태그로 층이 정해진다: [게이트] → exit 1 대상, [설명] → 파싱 제외,
    태그 없음 → 정보(표시만). 인용(>) 줄과 불릿의 이어지는 줄은 읽지 않는다.
    """
    out = []
    if not os.path.exists(md_path):
        return out
    skipping = False
    for line in open(md_path, encoding="utf-8"):
        s = line.rstrip("\n")
        if s.startswith(">"):
            continue
        m = re.match(r"^#{2,3}\s+(.*)$", s)
        if m:
            title = m.group(1).strip()
            skipping = SKIP_TAG in title
            gate = GATE_TAG in title
            sec = re.sub(r"^\d+\.\s*", "", title.replace(GATE_TAG, "").replace(SKIP_TAG, "")).strip()
            out.append((sec, [], gate))
            continue
        if skipping or not out or not s.startswith("- "):
            continue
        for piece in re.split(r"\s*/\s*|,\s*|\s·\s", s[2:]):
            term = clean_term(piece)
            if term:
                out[-1][1].append(term)
    return [(sec, list(dict.fromkeys(terms)), gate) for sec, terms, gate in out if terms]


def paragraphs(text):
    return [p.strip() for p in re.split(r"\n\s*\n", text)
            if p.strip() and not p.strip().startswith("#")]


def excerpts(paras, pattern, limit=4, width=18):
    """패턴이 걸린 자리를 ¶번호 + 앞뒤 문맥으로 뽑는다. 고치러 갈 수 있게."""
    out = []
    for i, p in enumerate(paras, 1):
        for m in pattern.finditer(p):
            a, b = max(0, m.start() - width), min(len(p), m.end() + width)
            frag = p[a:b].replace("\n", " ")
            out.append(f"¶{i}: …{frag}…")
            if len(out) >= limit:
                return out, True
    return out, False


def lost_items(before_text, after_text, pattern):
    fb, fa = Counter(pattern.findall(before_text)), Counter(pattern.findall(after_text))
    lost = {k: fb[k] - fa.get(k, 0) for k in fb if fa.get(k, 0) < fb[k]}
    added = {k: fa[k] - fb.get(k, 0) for k in fa if fa[k] > fb.get(k, 0)}
    return fb, lost, added


def content_tokens(sentence):
    toks = set()
    for w in re.findall(r"[가-힣]{2,}", sentence):
        w2 = STRIP_SUFFIX.sub("", w)
        if len(w2) >= 2:
            toks.add(w2)
    return toks


def redeclaration_chains(paras):
    """짧은 선언문이 3개 이상 이어지고, 그중 인접한 두 문장이 같은 내용어를 되풀이할 때."""
    chains = []
    for i, p in enumerate(paras, 1):
        sents = [s.strip() for s in SENT_SPLIT.split(p) if s.strip()]
        run = []

        def flush():
            if len(run) >= 3:
                toks = [content_tokens(s) for s in run]
                if any(toks[j] & toks[j + 1] for j in range(len(toks) - 1)):
                    chains.append((i, " ".join(run)))

        for s in sents:
            if len(re.sub(r"\s", "", s)) <= SHORT_SENT and s.endswith("다."):
                run.append(s)
            else:
                flush()
                run = []
        flush()
    return chains


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--after", required=True)
    ap.add_argument("--before")
    ap.add_argument("--protect", default="",
                    help='그 글의 주제어. 쉼표 구분 (예: "이 책,이 원고")')
    ap.add_argument("--phrases", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                      "..", "references", "phrases.md"))
    args = ap.parse_args()

    after = read(args.after)
    paras = paragraphs(after)
    total_chars = len(re.sub(r"\s", "", "".join(paras))) or 1
    protect = [t.strip() for t in args.protect.split(",") if t.strip()]
    exit_code = 0
    hard, fix, info = [], [], []
    print(f"── mary_gate v3 ── {args.after}  (본문 {total_chars}자, {len(paras)}문단)")
    if protect:
        print(f"   protect: {protect} (지시어·블록리스트 계수에서 제외)")
    print()

    # ── 1) 하드 게이트: 각주·숫자·직접 인용 (원본 대조)
    if args.before:
        before = read(args.before)

        fb, lost, added = lost_items(before, after, FOOTNOTE)
        if lost:
            det = " ".join(f"{k}(-{v})" for k, v in sorted(lost.items()))
            print(f"[실패] 각주 유실/감소: {det}  → 변환본 채택 금지. 복구 후 재측정.")
            exit_code = 2
            hard.append("각주")
        else:
            print(f"[통과] 각주 보존 {sum(fb.values())}회/{len(fb)}종 (등장 횟수까지 일치)")
        if added:
            det = " ".join(f"{k}(+{v})" for k, v in sorted(added.items()))
            print(f"[고침] 원본에 없던 각주 등장: {det}")
            exit_code = max(exit_code, 1)
            fix.append("각주추가")

        nb, lost, _ = lost_items(before, after, NUMBER)
        if lost:
            det = " ".join(f"{k}(-{v})" for k, v in sorted(lost.items()))
            print(f"[실패] 숫자 유실/감소: {det}  → 변환본 채택 금지. 숫자는 protected span이다.")
            exit_code = 2
            hard.append("숫자")
        else:
            print(f"[통과] 숫자 보존 {sum(nb.values())}회/{len(nb)}종")

        qb = Counter(QUOTE.findall(before))
        qa = Counter(QUOTE.findall(after))
        lost_q = [q for q in qb if qa.get(q, 0) < qb[q] and q not in after]
        if lost_q:
            print(f"[실패] 직접 인용 변형/유실 {len(lost_q)}건 → 변환본 채택 금지:")
            for q in lost_q[:5]:
                print(f"       “{q[:40]}{'…' if len(q) > 40 else ''}”")
            exit_code = 2
            hard.append("인용")
        else:
            print(f"[통과] 직접 인용 보존 {sum(qb.values())}건")

        lb, lost, _ = lost_items(before, after, LATIN)
        if lost:
            det = " ".join(f"{k}(-{v})" for k, v in sorted(lost.items())[:8])
            print(f"[고침] 영문 용어 유실: {det}  → 습관적 병기를 뺀 것이면 사유를 원장에, 용어면 복구.")
            exit_code = max(exit_code, 1)
            fix.append("영문용어")
        print()
    else:
        print("[안내] --before 없음 → 각주·숫자·인용 대조 생략(윤문 시엔 반드시 줄 것)\n")

    # ── 2) 부호 (md 파싱으로는 못 잡아서 코드가 직접 센다)
    em, en, mid = after.count("—"), after.count("–"), after.count("·")
    print(f"부호: — {em}개 / – {en}개 / · {mid}개")
    if em or en:
        for pat, name, c in ((re.compile("—"), "—", em), (re.compile("–"), "–", en)):
            if c:
                for e in excerpts(paras, pat, limit=3)[0]:
                    print(f"   {name} {e}")
        exit_code = max(exit_code, 1)
        fix.append("대시")
    if mid >= MIDDOT_INFO:
        print(f"   (참고) 미들닷 {mid}개 — 병기 관행({MIDDOT_INFO}개 미만)을 넘었다. 읽고 판단.")
        info.append("미들닷")
    print()

    # ── 3) 정정 골격 '아니라' (사용자 확정 기준 1: 기본 전면 해체)
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
        fix.append("아니라")
    print()

    # ── 4) 문두 접속부사 (사용자 확정 기준 2026-08-20)
    conj_head = lambda w: re.compile(rf"(?:^|[.?!\"”』」]\s*){w}[\s,]", re.M)
    hard_total, hard_lines = 0, []
    for w in HARD_CONJ:
        pat = conj_head(w)
        c = len(pat.findall(after))
        if c:
            hard_total += c
            hard_lines.append((w, c, pat))
    soft_counts = {w: len(conj_head(w).findall(after)) for w in SOFT_CONJ}
    print(f"문두 접속부사 — 경성 {hard_total}회 / 연성 " +
          " ".join(f"{w} {c}" for w, c in soft_counts.items()))
    if hard_total:
        for w, c, pat in hard_lines:
            print(f"   {w}: {c}회")
            for e in excerpts(paras, pat, limit=3)[0]:
                print(f"      {e}")
        print("   * 경성 접속부사는 어미(~지만/~니/~고/~는데)로 접거나 지운다. 인용문 내부만 사유 잔존.")
        exit_code = max(exit_code, 1)
        fix.append("접속부사")
    print()

    # ── 5) phrases.md 대조 — [게이트] 섹션만 판정, 나머지는 표시
    print("═══ phrases.md 블록리스트 대조 ([게이트] 섹션 = 고칠 목록 · 나머지 = 참고) ═══")
    gate_hits, info_hits = 0, 0
    for section, terms, gate in parse_phrases(args.phrases):
        found = []
        for t in terms:
            if t in protect:
                continue
            c = after.count(t)
            if c > 0:
                found.append((t, c, t in NOISY or len(t) <= 2))
        if not found:
            continue
        print(f"\n[{section}]{'  ← 게이트' if gate else '  (참고)'}")
        for t, c, noisy in sorted(found, key=lambda x: -x[1]):
            mark = "  ⚠오탐가능(내용어일 수 있음)" if noisy else ""
            print(f"   {t:<20} {c:>3}회{mark}")
            if gate and not noisy:
                gate_hits += 1
                for e in excerpts(paras, re.compile(re.escape(t)), limit=2)[0]:
                    print(f"      {e}")
            elif not noisy:
                info_hits += 1
    if gate_hits:
        exit_code = max(exit_code, 1)
        fix.append("블록리스트")
    if info_hits:
        info.append("블록리스트(참고)")
    print(f"\n게이트 검출 {gate_hits}종 · 참고 검출 {info_hits}종\n")

    # ── 6) 문단 지도: 글자수 + 쉼표 (상시 출력 — 작업 검증용)
    print("문단 지도 (글자수·쉼표 — 이 표를 결과 보고에 그대로 쓴다):")
    long_p = []
    for i, p in enumerate(paras, 1):
        L = len(re.sub(r"\s", "", p))
        c = p.count(",")
        marks = []
        if L >= PARA_LEN_WARN:
            marks.append(f"⚠길이{L}")
            long_p.append(i)
        if c >= PARA_COMMA_INFO:
            marks.append(f"(쉼표{c})")
        print(f"   ¶{i:>2}: {L:>4}자, 쉼표 {c:>2}개  {' '.join(marks)}")
    if long_p:
        exit_code = max(exit_code, 1)
        fix.append("문단길이")
        print("   * 공백 제외 450자 넘는 문단은 쪼갠다 (사용자 확정 기준 5).")
    heavy_s = [s.strip() for s in re.split(r"[.!?…]", "\n\n".join(paras))
               if s.count(",") >= SENT_COMMA_INFO]
    print(f"   한 문장 쉼표 {SENT_COMMA_INFO}개+: {len(heavy_s)}문장 (참고 — 읽고 판단)")
    for s in heavy_s[:5]:
        print(f"     [{s.count(',')}] {s[:44]}…")
    if heavy_s:
        info.append("문장쉼표")
    print()

    # ── 7) 지시어(이/그/저) 밀도 지도 + 나/내 밀도(정보)
    print(f"지시어 밀도 지도 ({PARA_DEMO_INFO}개+ 표시, {PARA_DEMO_WARN}개+ 고칠 목록):")
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
                if "지시어" not in fix:
                    fix.append("지시어")
            print(f"   ¶{i}: {c}개{hot}")
    if not shown:
        print("   없음")
    na_dense = [(i, len(NAE.findall(p))) for i, p in enumerate(paras, 1)]
    na_dense = [(i, c) for i, c in na_dense if c >= NAE_INFO]
    if na_dense:
        print(f"   나/내 계열 {NAE_INFO}개+ 문단(참고): "
              + " ".join(f"¶{i}({c})" for i, c in na_dense))
    print()

    # ── 8) 선언 연쇄 — 같은 내용어를 짧은 선언문으로 되풀이 (사용자 확정 기준 9)
    chains = redeclaration_chains(paras)
    print(f"선언 연쇄(짧은 선언문 3연속 + 인접 문장 내용어 재선언): {len(chains)}곳")
    for i, ch in chains[:5]:
        print(f"   ⚠ ¶{i}: {ch[:56]}…")
    if chains:
        exit_code = max(exit_code, 1)
        fix.append("선언연쇄")
        print("   * 같은 생각이면 한 문장으로 접는다. 재선언·도치 반복 금지.")
    print()

    # ── 9) 삼항 병렬 후보 (참고 — 구체·기능 삼항은 정상이라 판정에 넣지 않는다)
    tri = []
    for s in re.split(r"[.!?]", after):
        if len(re.findall(r"고,\s", s)) >= 2 \
           or re.search(r"[가-힣]+,\s*[가-힣]+,\s*[가-힣]+", s) and s.count(",") >= 2:
            tri.append(s.strip())
    tri = [t for t in tri if t][:12]
    print(f"삼항 병렬 후보: {len(tri)}개 (참고)")
    for t in tri[:6]:
        print(f"     {t[:52]}…")
    if tri:
        info.append("삼항(참고)")
        print("   * 추상 균형 삼항만 깬다. 구체·기능 삼항은 그대로.")
    print()

    # ── 판정
    verdict = {0: "통과", 1: "고칠 목록 있음 — 전수 처치 전 완료 선언 금지",
               2: "하드 위반 — 각주·숫자·인용 (변환본 채택 금지)", 3: "판정불가"}[exit_code]
    if hard:
        print(f"하드 위반: {', '.join(hard)}")
    if fix:
        print(f"고칠 목록: {', '.join(fix)}")
    if info:
        print(f"참고(판정 무관): {', '.join(info)}")
    print(f"══ 판정: exit {exit_code} = {verdict} ══")
    print("이 수치가 SSOT다. 고칠 목록은 발췌마다 고치거나, 못 고치면 문단 원장에 잔존 사유를 적는다.")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
