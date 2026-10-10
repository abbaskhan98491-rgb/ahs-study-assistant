"""Offline probe checks: synthetic facts and injectable transports only."""

from collections import Counter
import json
import threading
import unittest

from benchmark_providers import (
    BENCHMARK_PAGE, SYNTHETIC_PROMPT, run_benchmark, validate_synthetic_mcq,
)
from provider_transport import Candidate, Completion, ProviderError


def synthetic_question(**changes):
    item = {
        'question': 'What is the label of the blue token?',
        'options': ['BETA', 'GAMMA', 'ALPHA', 'DELTA'],
        'answer_index': 2,
        'explanation': 'The fictional source assigns ALPHA to the blue token.',
        'page': BENCHMARK_PAGE,
    }
    item.update(changes)
    return item


def candidate(provider, suffix='one'):
    return Candidate(id=f'offline:{provider.casefold()}:{suffix}',
                     provider=provider, model=f'offline-model-{suffix}',
                     api_key=f'fake-private-key-{provider}-{suffix}',
                     label=provider.title())


class SyntheticValidationTests(unittest.TestCase):
    def test_correct_known_fact_accepts_shuffled_and_normalized_options(self):
        for item in (
                synthetic_question(),
                synthetic_question(options=[' alpha ', 'beta', 'GAMMA', 'delta'], answer_index=0)):
            with self.subTest(options=item['options']):
                self.assertTrue(validate_synthetic_mcq(json.dumps([item])))

    def test_known_answer_source_and_complete_fields_are_required(self):
        invalid = [
            synthetic_question(answer_index=0),
            synthetic_question(answer_index=True),
            synthetic_question(answer_index=-1),
            synthetic_question(options=['ALPHA', 'ALPHA', 'GAMMA', 'DELTA'], answer_index=0),
            synthetic_question(page='unrelated-source, page 1'),
            synthetic_question(page='synthetic-benchmark, page 2'),
            synthetic_question(explanation=''),
            synthetic_question(explanation=None),
            synthetic_question(question='What is the label of the green token?'),
            synthetic_question(question='Which label is NOT assigned to the blue token?'),
        ]
        missing_explanation = synthetic_question()
        missing_explanation.pop('explanation')
        invalid.append(missing_explanation)
        for item in invalid:
            with self.subTest(item=item):
                self.assertFalse(validate_synthetic_mcq(json.dumps([item])))

    def test_only_one_complete_json_object_in_an_array_is_accepted(self):
        valid = json.dumps([synthetic_question()])
        for raw in (None, '', valid[:-1], '```json\n' + valid + '\n```',
                    json.dumps(synthetic_question()), json.dumps([]),
                    json.dumps([synthetic_question(), synthetic_question()]), json.dumps([None])):
            with self.subTest(raw=raw):
                self.assertFalse(validate_synthetic_mcq(raw))


class BenchmarkExecutionTests(unittest.TestCase):
    def test_one_identical_bounded_completion_per_provider_without_fallbacks(self):
        selected = [candidate('cerebras'), candidate('groq'), candidate('gemini')]
        all_candidates = [selected[0], candidate('CEREBRAS', 'two'), selected[1],
                          candidate('groq', 'two'), selected[2], candidate('gemini', 'two'),
                          candidate('unknown')]
        calls = []
        lock = threading.Lock()
        raw = json.dumps([synthetic_question()])

        def complete(fake_candidate, prompt, **kwargs):
            with lock:
                calls.append((fake_candidate, prompt, kwargs))
            return Completion(raw, fake_candidate.label, fake_candidate.model, .125, 70)

        profile, rows = run_benchmark(all_candidates, completion_fn=complete)
        self.assertEqual(Counter(item[0].provider.casefold() for item in calls),
                         {'cerebras': 1, 'groq': 1, 'gemini': 1})
        self.assertEqual({item[0].id for item in calls}, {item.id for item in selected})
        for fake_candidate, prompt, kwargs in calls:
            self.assertEqual(prompt, SYNTHETIC_PROMPT)
            self.assertEqual(kwargs, {'max_tokens': 400, 'temperature': 0.0, 'timeout_seconds': 20.0})
            self.assertEqual(profile['stats'][fake_candidate.id]['mcq']['samples'], 1)
        self.assertEqual(profile['schema'], 1)
        self.assertEqual(profile['cooldowns'], {})
        self.assertEqual([row['provider'] for row in rows], ['Cerebras', 'Groq', 'Gemini'])
        for row in rows:
            self.assertEqual(set(row), {'provider', 'model', 'seconds', 'status', 'valid_json'})
            self.assertEqual(row['status'], 'valid')
            self.assertTrue(row['valid_json'])
            self.assertEqual(row['seconds'], .125)
        serialized = json.dumps((profile, rows))
        for item in all_candidates:
            self.assertNotIn(item.api_key, serialized)
        self.assertNotIn(SYNTHETIC_PROMPT, serialized)
        self.assertNotIn(raw, serialized)

    def test_failures_are_sanitized_not_retried_or_recorded_as_valid_speed(self):
        candidates = [candidate('cerebras'), candidate('groq'), candidate('gemini')]
        attempts = []
        lock = threading.Lock()
        private_detail = 'fake-private-detail-must-not-escape'

        def complete(fake_candidate, prompt, **kwargs):
            with lock:
                attempts.append(fake_candidate.provider)
            if fake_candidate.provider == 'cerebras':
                return Completion(json.dumps([synthetic_question(answer_index=0)]),
                                  'Cerebras', fake_candidate.model, .05, 70)
            if fake_candidate.provider == 'groq':
                raise ProviderError(private_detail, kind='rate_limit', status_code=429, retry_after=90)
            raise RuntimeError(private_detail)

        profile, rows = run_benchmark(candidates, completion_fn=complete)
        self.assertEqual(Counter(attempts), {'cerebras': 1, 'groq': 1, 'gemini': 1})
        self.assertEqual({row['provider']: row['status'] for row in rows},
                         {'Cerebras': 'invalid', 'Groq': 'rate_limit', 'Gemini': 'unavailable'})
        self.assertTrue(all(row['valid_json'] is False for row in rows))
        self.assertEqual(profile['stats'], {})
        self.assertTrue(profile['cooldowns'])
        serialized = json.dumps((profile, rows))
        self.assertNotIn(private_detail, serialized)
        for item in candidates:
            self.assertNotIn(item.api_key, serialized)

    def test_no_configured_provider_does_not_call_transport(self):
        def unexpected(*args, **kwargs):
            self.fail('An empty probe must not call a provider')
        profile, rows = run_benchmark([], completion_fn=unexpected)
        self.assertEqual(rows, ())
        self.assertEqual(profile['schema'], 1)
        self.assertEqual(profile['stats'], {})
        self.assertEqual(profile['cooldowns'], {})


if __name__ == '__main__':
    unittest.main()
