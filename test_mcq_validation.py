"""Offline checks for ambiguous component lists without rejecting ordered tasks."""

import json
import unittest

from study_utils import parse_mcqs


BOOK = 'Offline-Slides.pdf'
CONTEXT = f'[{BOOK}, page 7]\nThe lesson lists several components.'
MENINGES = [
    'Dura mater, arachnoid mater, pia mater',
    'Pia mater, dura mater, arachnoid mater',
    'Arachnoid mater, pia mater, dura mater',
    'Dura mater, pia mater, arachnoid mater',
]


def item(question='Which are the three layers of the meninges?', options=None):
    return dict(question=question, options=MENINGES[:] if options is None else options,
                answer_index=0, explanation='The source supplies the components.',
                page=f'{BOOK}, page 7')


def parsed(question):
    return parse_mcqs(json.dumps([question]), BOOK, CONTEXT)


class ComponentValidationTests(unittest.TestCase):
    def test_bare_ganglion_count_is_rejected(self):
        question = item(question='How many cervical ganglia are present on each side?',
                        options=['Five', 'Six', 'Seven', 'Eight'])
        self.assertEqual(parsed(question), [])

    def test_explicit_original_and_fused_count_scopes_are_preserved(self):
        for stem in ('How many original cervical ganglia are present before fusion?',
                     'The number of named cervical ganglia groups after fusion is'):
            with self.subTest(stem=stem):
                question = item(question=stem, options=['Two', 'Three', 'Four', 'Eight'])
                self.assertEqual(parsed(question), [question])

    def test_other_numerical_questions_are_preserved(self):
        question = item(question='How many layers of meninges surround the brain?',
                        options=['Two', 'Three', 'Four', 'Five'])
        self.assertEqual(parsed(question), [question])

    def test_spinal_root_synonyms_do_not_make_distinct_options(self):
        question = item(question='Preganglionic fibers leave the spinal cord through',
                        options=['Anterior nerve root', 'Posterior nerve root',
                                 'Dorsal root', 'Ventral root'])
        self.assertEqual(parsed(question), [])

    def test_distinct_root_choices_remain_valid(self):
        question = item(question='The spinal nerve fibers leave through',
                        options=['Anterior root', 'Posterior root', 'Spinal canal', 'Dorsal horn'])
        self.assertEqual(parsed(question), [question])

    def test_directional_adjectives_are_not_globally_treated_as_synonyms(self):
        question = item(question='Which parts of the brain are shown?',
                        options=['Anterior surface', 'Ventral surface',
                                 'Posterior surface', 'Dorsal surface'])
        self.assertEqual(parsed(question), [question])

    def test_reordered_identical_member_lists_are_rejected(self):
        self.assertEqual(parsed(item()), [])
        self.assertEqual(parsed(item(question='Meninges consist of')), [])

    def test_two_equivalent_options_are_enough_to_make_a_list_ambiguous(self):
        options = ['Alpha, Beta, Gamma', 'Gamma, Alpha, Beta',
                   'Alpha, Beta, Delta', 'Alpha, Gamma, Delta']
        self.assertEqual(parsed(item(question='Which components form the set?', options=options)), [])

    def test_whitespace_case_and_final_and_do_not_make_different_members(self):
        options = ['Alpha, Beta, Gamma', ' gamma , ALPHA, and beta ',
                   'Alpha, Beta, Delta', 'Alpha, Gamma, Delta']
        self.assertEqual(parsed(item(question='Which members are included?', options=options)), [])

    def test_different_component_lists_remain_valid_without_option_mutation(self):
        question = item(options=['Dura mater, arachnoid mater, pia mater',
                                 'Dura mater, arachnoid mater, ependyma',
                                 'Dura mater, ependyma, pia mater',
                                 'Ependyma, arachnoid mater, pia mater'])
        self.assertEqual(parsed(question), [question])

    def test_explicit_order_and_position_questions_accept_permutations(self):
        for stem in ('Which sequence gives the layers in their correct order?',
                     'Arrange the layers from outermost to innermost.',
                     'Which layers run from superficial to deep?'):
            with self.subTest(stem=stem):
                question = item(question=stem)
                self.assertEqual(parsed(question), [question])

    def test_english_sequence_and_non_member_sentence_questions_are_preserved(self):
        options = ['subject, verb, object', 'verb, subject, object',
                   'object, subject, verb', 'subject, object, verb']
        question = item(question='Which sequence is the correct order of sentence parts?', options=options)
        self.assertEqual(parsed(question), [question])
        question = item(question='Which sentence uses punctuation correctly?',
                        options=['First clause, second clause', 'Second clause, first clause',
                                 'Third clause, fourth clause', 'Fourth clause, third clause'])
        self.assertEqual(parsed(question), [question])

    def test_whole_component_word_order_is_not_discarded(self):
        question = item(question='Which parts contain the intended statements?', options=[
            'John sees Mary, Paul helps Tom', 'Mary sees John, Paul helps Tom',
            'John sees Mary, Tom helps Paul', 'Mary sees John, Tom helps Paul'])
        self.assertEqual(parsed(question), [question])

    def test_old_option_labels_are_preserved_but_do_not_hide_duplicate_lists(self):
        labels = ['A. ', 'B) ', 'C ', 'D. ']
        question = item(options=[label + option for label, option in zip(labels, MENINGES)])
        self.assertEqual(parsed(question), [])
        question = item(options=['A. Alpha, Beta', 'B) Alpha, Gamma',
                                 'C Alpha, Delta', 'D. Beta, Gamma'])
        self.assertEqual(parsed(question), [question])


if __name__ == '__main__':
    unittest.main()
