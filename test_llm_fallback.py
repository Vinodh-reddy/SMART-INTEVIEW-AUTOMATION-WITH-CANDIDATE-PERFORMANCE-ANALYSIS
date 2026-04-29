from django.test import TestCase, Client
from django.urls import reverse
from types import SimpleNamespace
import sys

# Provide lightweight stubs for LLM-related modules so importing views does not require the real package
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


class LLMFallbackTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_start_interview_uses_fallback_on_llm_error(self):
        # Make generate_question raise to simulate network/DNS failure
        original = views.generate_question
        def bad(*a, **k):
            raise Exception("network error: getaddrinfo failed")
        views.generate_question = bad

        try:
            resp = self.client.post(reverse('start_interview'), data={
                'name': 'Test', 'email': 'a@example.com', 'job_description': 'Test role'
            }, follow=True)
            # Should render question page and contain offline marker
            self.assertContains(resp, '(Offline)')
        finally:
            views.generate_question = original

    def test_next_question_uses_fallback_on_llm_error(self):
        # Start a normal interview using a harmless generate_question
        original = views.generate_question
        views.generate_question = lambda msgs, jd: "[MCQ] Simple?\nA) X\nB) Y\nC) Z\nD) W"

        try:
            resp = self.client.post(reverse('start_interview'), data={
                'name': 'Test2', 'email': 'b@example.com', 'job_description': 'Role'
            }, follow=True)
            # Now make generate_question fail for next question
            views.generate_question = lambda msgs, jd: (_ for _ in ()).throw(Exception('fail'))

            resp2 = self.client.post(reverse('answer_question'), data={'answer': 'B'}, follow=True)
            self.assertContains(resp2, '(Offline)')
        finally:
            views.generate_question = original
