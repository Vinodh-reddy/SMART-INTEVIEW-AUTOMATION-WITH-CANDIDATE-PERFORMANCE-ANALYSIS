from types import SimpleNamespace
from django.test import TestCase
import sys

# Provide lightweight stubs for LLM-related modules so tests can import views
sys.modules['langchain_google_genai'] = SimpleNamespace(
    ChatGoogleGenerativeAI=lambda **kwargs: SimpleNamespace(invoke=lambda msgs: SimpleNamespace(content=''))
)
messages_mod = SimpleNamespace(
    HumanMessage=lambda content=None: SimpleNamespace(content=content),
    SystemMessage=lambda content=None: SimpleNamespace(content=content)
)
sys.modules['langchain_core'] = SimpleNamespace(messages=messages_mod)
sys.modules['langchain_core.messages'] = messages_mod

from users import views


class MCQEvaluationTests(TestCase):
    def test_mcq_correct_letter_scores_5(self):
        question = "[MCQ] Which color mixes with blue to make green?\nA) Red\nB) Yellow\nC) Purple\nD) Orange"

        # Mock llm.invoke to return 'B' as correct
        original_invoke = views.llm.invoke
        views.llm.invoke = lambda msgs: SimpleNamespace(content='B')

        try:
            res = views.evaluate_answer(question, 'B')
            self.assertEqual(res['score'], 5)
            self.assertEqual(res['qualified'], 'yes')
        finally:
            views.llm.invoke = original_invoke

    def test_mcq_full_text_answer_matches_and_scores_5(self):
        question = "[MCQ] Pick the fruit.\nA) Apple\nB) Carrot\nC) Potato\nD) Tomato"

        original_invoke = views.llm.invoke
        views.llm.invoke = lambda msgs: SimpleNamespace(content='A')

        try:
            res = views.evaluate_answer(question, 'Apple')
            self.assertEqual(res['score'], 5)
            self.assertEqual(res['qualified'], 'yes')
        finally:
            views.llm.invoke = original_invoke

    def test_mcq_incorrect_scores_0(self):
        question = "[MCQ] What is 2+2?\nA) 3\nB) 4\nC) 5\nD) 22"

        original_invoke = views.llm.invoke
        views.llm.invoke = lambda msgs: SimpleNamespace(content='B')

        try:
            res = views.evaluate_answer(question, 'A')
            self.assertEqual(res['score'], 0)
            self.assertEqual(res['qualified'], 'no')
        finally:
            views.llm.invoke = original_invoke

    def test_inline_numeric_options_and_numeric_answer_scores_5(self):
        question = "Which is prime? Options: 1) 4, 2) 5, 3) 6, 4) 8"

        original_invoke = views.llm.invoke
        views.llm.invoke = lambda msgs: SimpleNamespace(content='2')

        try:
            res = views.evaluate_answer(question, '2')
            self.assertEqual(res['score'], 5)
            self.assertEqual(res['qualified'], 'yes')
        finally:
            views.llm.invoke = original_invoke

    def test_comma_separated_options_and_text_answer_matches(self):
        question = "Pick a color. Options: Red, Blue, Green, Yellow"

        original_invoke = views.llm.invoke
        views.llm.invoke = lambda msgs: SimpleNamespace(content='B')

        try:
            res = views.evaluate_answer(question, 'blue')
            self.assertEqual(res['score'], 5)
            self.assertEqual(res['qualified'], 'yes')
        finally:
            views.llm.invoke = original_invoke

    def test_label_variants_c_parses(self):
        question = "Which is largest?\nA- small\nB- medium\nC- large\nD- huge"

        original_invoke = views.llm.invoke
        views.llm.invoke = lambda msgs: SimpleNamespace(content='C')

        try:
            res = views.evaluate_answer(question, 'C) large')
            self.assertEqual(res['score'], 5)
            self.assertEqual(res['qualified'], 'yes')
        finally:
            views.llm.invoke = original_invoke