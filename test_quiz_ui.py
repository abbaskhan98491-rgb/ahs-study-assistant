"""Offline interaction regressions for simple MCQ practice."""

from pathlib import Path
import os
import re
import socket
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest


def questions(count):
    return [
        {
            "question": f"Which answer is correct for question {index + 1}?",
            "options": [f"Correct {index}", f"Other {index}", f"Third {index}", f"Fourth {index}"],
            "answer_index": 0,
            "explanation": f"Explanation for question {index + 1}.",
            "page": f"Source.pdf, page {index + 1}",
        }
        for index in range(count)
    ]


class MCQPracticeTests(unittest.TestCase):
    def app(self, count=12):
        # Known workspace paths avoid temporary-directory ACL issues and keep
        # concurrent root/agent runs from overwriting each other's fixture.
        path = Path(f"tmp/mcq_ui_regression_{os.getpid()}_{self._testMethodName}.py")
        path.parent.mkdir(exist_ok=True)
        path.write_text(
            "import streamlit as st\n"
            "from quiz_ui import render_mcqs\n"
            "st.toggle('Dark mode', key='test_dark')\n"
            "st.toggle('Show MCQs', key='test_show', value=True)\n"
            "if st.button('New set', key='test_new'):\n"
            "    st.session_state['generation'] = st.session_state.get('generation', 0) + 1\n"
            "if st.button('Append questions', key='test_append'):\n"
            "    st.session_state['extra_questions'] = True\n"
            f"all_questions = {questions(count + 3)!r}\n"
            f"mcqs = all_questions if st.session_state.get('extra_questions') else all_questions[:{count}]\n"
            "if st.session_state['test_show']:\n"
            "    render_mcqs(mcqs, st.session_state.get('generation', 0), 'Circulation')\n",
            encoding="utf-8",
        )
        self.addCleanup(path.unlink, missing_ok=True)
        at = AppTest.from_file(str(path.resolve()), default_timeout=20).run()
        self.assertEqual(len(at.exception), 0)
        return at

    def state(self, at):
        return at.session_state['_mcq_answer_state']

    def test_all_forty_questions_visible_without_quiz_controls(self):
        at = self.app(40)
        self.assertEqual(len(at.radio), 40)
        self.assertEqual([radio.key for radio in at.radio], [f'ans_{i}' for i in range(40)])
        self.assertEqual([button.key for button in at.button], ['test_new', 'test_append'])
        self.assertEqual(len(at.metric), 0)
        self.assertEqual(len(at.get('progress')), 0)
        self.assertEqual(len(at.get('form')), 0)
        visible_text = '\n'.join(re.sub(r'<[^>]*>', '', element.value) for element in [*at.markdown, *at.caption])
        for forbidden in ('quiz', 'submit', 'retry', 'score', 'page', 'attempt', 'answered'):
            self.assertNotIn(forbidden, visible_text.casefold())

    def test_correct_answer_feedback_is_immediate(self):
        at = self.app()
        self.assertEqual(len(at.success), 0)
        self.assertEqual(len(at.error), 0)
        self.assertFalse(any('Explanation:' in element.value for element in at.markdown))
        at.radio(key='ans_0').set_value('Correct 0').run()
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(len(at.success), 1)
        self.assertIn('Correct. Correct answer: Correct 0', at.success[0].value)
        self.assertIn('Explanation: Explanation for question 1.', at.success[0].value)
        self.assertIn('Reference: Source.pdf, page 1', [caption.value for caption in at.caption])

    def test_wrong_answer_shows_correct_option_and_selection_changes_status(self):
        at = self.app()
        at.radio(key='ans_0').set_value('Other 0').run()
        self.assertEqual(len(at.error), 1)
        self.assertIn('Incorrect. Correct answer: Correct 0', at.error[0].value)
        self.assertIn('Explanation: Explanation for question 1.', at.error[0].value)
        at.radio(key='ans_0').set_value('Correct 0').run()
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(len(at.error), 0)
        self.assertEqual(len(at.success), 1)
        self.assertIn('Correct. Correct answer: Correct 0', at.success[0].value)

    def test_feedback_survives_theme_change_and_hiding_the_list(self):
        at = self.app()
        at.radio(key='ans_0').set_value('Other 0')
        at.toggle(key='test_dark').set_value(True).run()
        self.assertEqual(at.radio(key='ans_0').value, 'Other 0')
        self.assertIn('Incorrect. Correct answer: Correct 0', at.error[0].value)
        at.toggle(key='test_show').set_value(False).run()
        self.assertEqual(len(at.radio), 0)
        at.toggle(key='test_show').set_value(True).run()
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(at.radio(key='ans_0').value, 'Other 0')
        self.assertIn('Explanation: Explanation for question 1.', at.error[0].value)
        self.assertEqual(self.state(at)['answers'], {0: 'Other 0'})

    def test_appending_questions_preserves_answers_and_feedback(self):
        at = self.app(2)
        at.radio(key='ans_1').set_value('Correct 1').run()
        at.button(key='test_append').click().run()
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(len(at.radio), 5)
        self.assertEqual(at.radio(key='ans_1').value, 'Correct 1')
        self.assertTrue(all(at.radio(key=f'ans_{i}').value is None for i in range(2, 5)))
        self.assertIn('Explanation: Explanation for question 2.', at.success[0].value)
        at.radio(key='ans_4').set_value('Other 4').run()
        self.assertEqual(self.state(at)['answers'], {1: 'Correct 1', 4: 'Other 4'})
        self.assertIn('Explanation: Explanation for question 5.', at.error[0].value)

    def test_new_generation_clears_selections_and_feedback(self):
        at = self.app()
        at.radio(key='ans_0').set_value('Correct 0').run()
        at.radio(key='ans_11').set_value('Other 11').run()
        at.button(key='test_new').click().run()
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(self.state(at)['set_id'], '1')
        self.assertEqual(self.state(at)['answers'], {})
        self.assertTrue(all(radio.value is None for radio in at.radio))
        self.assertEqual(len(at.success), 0)
        self.assertEqual(len(at.error), 0)
        self.assertFalse(any('Reference:' in caption.value for caption in at.caption))

    def test_rendering_and_feedback_work_with_network_blocked(self):
        original_connect = socket.socket.connect

        def local_connect(sock, address):
            # Windows asyncio creates a loopback socket pair for AppTest itself.
            if isinstance(address, tuple) and address[0] in ('127.0.0.1', '::1', 'localhost'):
                return original_connect(sock, address)
            raise AssertionError('MCQ practice must work without an external provider')

        with patch('socket.socket.connect', new=local_connect):
            at = self.app(1)
            at.radio(key='ans_0').set_value('Other 0').run()
        self.assertEqual(len(at.exception), 0)
        self.assertIn('Explanation for question 1.', at.error[0].value)


if __name__ == '__main__':
    unittest.main()
