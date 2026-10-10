"""Answer placement regressions, including order-dependent option semantics."""

from collections import Counter
from copy import deepcopy
import random
import re
import unittest

from mcq_order import balance_mcq_options


def item(index=0, **changes):
    question = {
        "question": f"Which structure performs function {index}?",
        "options": [f"Correct {index}", f"Other {index}", f"Third {index}", f"Fourth {index}"],
        "answer_index": 0,
        "explanation": f"Structure {index} performs this function.",
        "page": f"Source.pdf, page {index + 1}",
        "metadata": {"source": ["book"]},
    }
    question.update(changes)
    return question


class AnswerOrderTests(unittest.TestCase):
    def test_forty_first_answers_are_evenly_balanced_without_changing_facts(self):
        original = [item(index) for index in range(40)]
        snapshot = deepcopy(original)
        result = balance_mcq_options(original, rng=random.Random(9))
        self.assertEqual(Counter(question['answer_index'] for question in result), {0: 10, 1: 10, 2: 10, 3: 10})
        for before, after in zip(original, result):
            self.assertEqual(after['options'][after['answer_index']], before['options'][0])
            self.assertCountEqual(after['options'], before['options'])
            self.assertEqual(after['explanation'], before['explanation'])
            self.assertEqual(after['page'], before['page'])
            self.assertNotIn('option_order_warning', after)
        self.assertEqual(original, snapshot)
        result[0]['metadata']['source'].append('changed')
        self.assertEqual(original, snapshot)
        targets = [question['answer_index'] for question in result]
        self.assertNotEqual(targets, targets[:4] * 10)
        self.assertTrue(any(len(set(targets[index:index + 4])) < 4 for index in range(0, 40, 4)))

    def test_partial_sets_balanced_and_new_random_seed_changes_order(self):
        first = balance_mcq_options([item(index) for index in range(11)], rng=random.Random(1))
        second = balance_mcq_options([item(index) for index in range(11)], rng=random.Random(2))
        counts = Counter(question['answer_index'] for question in first)
        self.assertLessEqual(max(counts.values()) - min(counts.values()), 1)
        self.assertNotEqual([q['options'] for q in first], [q['options'] for q in second])

    def test_appended_questions_preserve_prefix_and_existing_answer_strings(self):
        prefix = [item(index) for index in range(8)]
        prefix_snapshot = deepcopy(prefix)
        answers = {0: prefix[0]['options'][0], 7: prefix[7]['options'][1]}
        tail = balance_mcq_options([item(index) for index in range(8, 40)], prefix, random.Random(3))
        combined = prefix + tail
        self.assertEqual(prefix, prefix_snapshot)
        self.assertEqual(combined[:8], prefix_snapshot)
        self.assertEqual(answers, {0: 'Correct 0', 7: 'Other 7'})
        self.assertEqual(Counter(q['answer_index'] for q in combined), {0: 10, 1: 10, 2: 10, 3: 10})

    def test_combining_options_expand_original_meanings_and_explanation_letters(self):
        original = item(options=['Sodium', 'Potassium', 'Both A and B', 'Calcium'],
                        answer_index=2, explanation='Option C is correct because options A and B are needed.')
        for seed in range(20):
            result = balance_mcq_options([original], rng=random.Random(seed))[0]
            self.assertEqual(result['options'][result['answer_index']], 'Both “Sodium” and “Potassium”')
            self.assertIn('“Both “Sodium” and “Potassium”” is correct', result['explanation'])
            self.assertIn('“Sodium” and “Potassium” are needed', result['explanation'])
            self.assertNotIn('option_order_warning', result)

    def test_middle_above_reference_does_not_include_original_later_option(self):
        original = item(options=['Sodium', 'Potassium', 'None of the above', 'Calcium'], answer_index=2)
        result = balance_mcq_options([original], rng=random.Random(5))[0]
        correct = result['options'][result['answer_index']]
        self.assertEqual(correct, 'None of these: “Sodium”; “Potassium”')
        self.assertNotIn('Calcium', correct)
        original['options'][2] = 'All of the above'
        result = balance_mcq_options([original], rng=random.Random(5))[0]
        self.assertEqual(result['options'][result['answer_index']], 'All of these: “Sodium”; “Potassium”')

    def test_bare_letter_pair_and_labeled_options_expand_safely(self):
        original = item(options=['A. Sodium', 'B. Potassium', 'C. Calcium', 'D. A and C'], answer_index=3,
                        explanation='D is correct.')
        result = balance_mcq_options([original], rng=random.Random(2))[0]
        self.assertEqual(result['options'][result['answer_index']], 'Both “Sodium” and “Calcium”')
        self.assertEqual(result['explanation'], '“Both “Sodium” and “Calcium”” is correct.')

    def test_unsafe_cycles_and_unrecognized_relative_refs_keep_original_order(self):
        cases = [
            item(options=['Both B and C', 'Both A and D', 'Sodium', 'Potassium']),
            item(options=['Sodium', 'Potassium', 'All of above except B', 'Calcium']),
            item(explanation='The first option is correct.'),
            item(explanation='B supports the correct option.'),
        ]
        for original in cases:
            with self.subTest(original=original):
                result = balance_mcq_options([original], rng=random.Random(7))[0]
                self.assertEqual(result['options'], original['options'])
                self.assertEqual(result['answer_index'], original['answer_index'])
                self.assertEqual(result['explanation'], original['explanation'])
                self.assertTrue(result['option_order_warning'])

    def test_vitamin_letter_is_a_fact_not_an_answer_label(self):
        original = item(options=['Vitamin A', 'Vitamin D', 'Vitamin E', 'Vitamin K'],
                        explanation='Vitamin A is important for vision.')
        result = balance_mcq_options([original], rng=random.Random(4))[0]
        self.assertEqual(result['options'][result['answer_index']], 'Vitamin A')
        self.assertEqual(result['explanation'], original['explanation'])
        self.assertNotIn('option_order_warning', result)

    def test_space_separated_provider_labels_are_removed_before_balancing(self):
        questions = [item(index, options=[f'A Correct {index}', f'B Other {index}',
                                         f'C Third {index}', f'D Fourth {index}'],
                          _option_order_version=1) for index in range(40)]
        result = balance_mcq_options(questions, rng=random.Random(6))
        self.assertEqual(Counter(q['answer_index'] for q in result), {0: 10, 1: 10, 2: 10, 3: 10})
        for index, q in enumerate(result):
            self.assertEqual(q['options'][q['answer_index']], f'Correct {index}')
            self.assertFalse(any(re.match(r'^[A-D]\s+', option) for option in q['options']))
            self.assertNotIn('option_order_warning', q)
            self.assertEqual(q['_option_order_version'], 2)

    def test_factual_space_separated_letters_are_not_removed(self):
        original = item(options=['A band', 'B cells', 'C fibers', 'D waves'])
        result = balance_mcq_options([original], rng=random.Random(6))[0]
        self.assertEqual(result['options'], original['options'])
        self.assertTrue(result['option_order_warning'])


if __name__ == '__main__':
    unittest.main()
