# -*- coding: utf-8 -*-
"""mary_gate.py 회귀 테스트 — 표준 라이브러리만. `python -m unittest discover tests`.

세 가지를 고정한다:
1. 사람이 쓴 평범한 글은 exit 0 이어야 한다 (게이트가 늘 exit 1이면 무시된다).
2. 전형적인 AI 글은 exit 1 이고, 걸린 축이 사용자 확정 기준이어야 한다.
3. 각주·숫자·직접 인용이 사라지면 exit 2 (채택 금지) 이어야 한다.
그리고 Windows 한글 콘솔(cp949)에서 죽지 않아야 한다.
"""
import os, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
GATE = os.path.join(HERE, "..", "scripts", "mary_gate.py")

HUMAN = """어제는 비가 왔다. 우산을 안 챙겨서 편의점 앞에서 십 분쯤 서 있었는데, 옆에 있던 아저씨가 담배를 두 대 피우는 동안 나는 그냥 빗소리를 들었다.

집에 오니 여덟 시였다. 밥은 없고 라면은 있었다. 끓이면서 어머니한테 전화를 했고, 별 얘기는 안 했다. 김치 남았냐고, 남았다고, 그게 다였다.

그래도 그날은 나쁘지 않았다. 책상 위에서 지난달 영수증을 정리하다가 잊고 있던 3만 원짜리 상품권을 찾았다.[^1] 유효기간은 2026년 12월까지라고 “본 상품권은 현금으로 교환되지 않습니다”라는 문구 옆에 적혀 있었다.

[^1]: 2025년 12월에 받은 것이다.
"""

AI = """오늘날 우리는 단순한 정보의 소비자가 아니라 능동적인 창조자로서의 역할을 요구받고 있다. 그러나 이러한 변화는 기회이자 동시에 도전이다. 중요한 것은 기술 그 자체가 아니라, 그것을 어떻게 활용하느냐이다.

이는 개인의 차원을 넘어 조직, 사회, 그리고 문명의 차원에서 재정의되어야 한다. 또한 우리는 속도가 아니라 방향을 봐야 한다. 따라서 진정한 혁신은 도구가 아니라 태도에서 시작된다 — 그것이 핵심이다.

결국 남는 것은 사람이다. 사람이 곧 답이다. 답은 늘 가까이 있다.
"""


def run(after, before=None, env_extra=None):
    with tempfile.TemporaryDirectory() as d:
        a = os.path.join(d, "after.md")
        with open(a, "w", encoding="utf-8") as f:
            f.write(after)
        cmd = [sys.executable, GATE, "--after", a]
        if before is not None:
            b = os.path.join(d, "before.md")
            with open(b, "w", encoding="utf-8") as f:
                f.write(before)
            cmd += ["--before", b]
        env = dict(os.environ)
        env.pop("PYTHONUTF8", None)
        env.pop("PYTHONIOENCODING", None)
        if env_extra:
            env.update(env_extra)
        p = subprocess.run(cmd, capture_output=True, env=env)
        return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")


class GateTests(unittest.TestCase):
    def test_human_prose_passes(self):
        code, out, err = run(HUMAN, HUMAN)
        self.assertEqual(code, 0, out + err)
        self.assertIn("각주 보존", out)
        self.assertIn("숫자 보존", out)
        self.assertNotIn("선언 연쇄(짧은 선언문 3연속 + 인접 문장 내용어 재선언): 1", out)

    def test_ai_prose_lists_user_confirmed_axes(self):
        code, out, err = run(AI, AI)
        self.assertEqual(code, 1, out + err)
        for axis in ("대시", "아니라", "접속부사", "블록리스트", "선언연쇄"):
            self.assertIn(axis, out.split("고칠 목록:")[1].splitlines()[0], out)
        self.assertIn("중요한 것은", out)

    def test_footnote_loss_is_hard(self):
        code, out, _ = run(HUMAN.replace("[^1]", "", 1), HUMAN)
        self.assertEqual(code, 2)
        self.assertIn("각주 유실", out)

    def test_number_loss_is_hard(self):
        code, out, _ = run(HUMAN.replace("3만 원", "삼만 원"), HUMAN)
        self.assertEqual(code, 2)
        self.assertIn("숫자 유실", out)

    def test_quote_change_is_hard(self):
        code, out, _ = run(HUMAN.replace("현금으로 교환되지", "현금으로 바꿔 주지"), HUMAN)
        self.assertEqual(code, 2)
        self.assertIn("직접 인용", out)

    def test_number_moved_is_fine(self):
        moved = HUMAN.replace("3만 원짜리 상품권을 찾았다", "상품권을 찾았다. 3만 원짜리였다")
        code, out, _ = run(moved, HUMAN)
        self.assertNotEqual(code, 2, out)

    def test_survives_cp949_console(self):
        code, out, err = run(HUMAN, HUMAN, {"PYTHONIOENCODING": "cp949"})
        self.assertEqual(code, 0, err)
        self.assertNotIn("UnicodeEncodeError", err)
        self.assertIn("판정", out)

    def test_missing_file_is_3(self):
        p = subprocess.run([sys.executable, GATE, "--after", "no-such-file.md"], capture_output=True)
        self.assertEqual(p.returncode, 3)


if __name__ == "__main__":
    unittest.main()
