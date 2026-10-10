"""Offline routing regressions: quality gates, learning, wait bounds and cooldowns."""

import json
from pathlib import Path
import unittest
from unittest.mock import patch

import provider_router as router
from provider_transport import Completion, ProviderError


KEYS = dict(groq_keys=['test-groq-key'], cerebras_key='test-cerebras-key', gemini_key='test-gemini-key')


def answer(candidate, text='Valid answer ' * 90, elapsed=1):
    return Completion(text, candidate.label, candidate.model, elapsed, 200)


class RoutingTests(unittest.TestCase):
    def test_current_models_no_network_during_candidate_build_and_family_fairness(self):
        with patch.object(router, 'complete', side_effect=AssertionError('Network')), \
             patch.object(router, 'discover_gemini_models', side_effect=AssertionError('Lookup')):
            candidates = router.build_candidates(**{**KEYS, 'groq_keys': ['first', 'second', 'first']})
        self.assertEqual([c.provider for c in candidates[:3]], ['cerebras', 'groq', 'gemini'])
        self.assertNotIn('llama-3.1-8b-instant', [c.model for c in candidates])
        self.assertNotIn('llama-3.3-70b', [c.model for c in candidates])
        self.assertEqual(candidates[1].model, 'openai/gpt-oss-20b')
        study = router.build_candidates(**KEYS, task='topic')
        self.assertNotIn('openai/gpt-oss-20b', [c.model for c in study])

    def test_success_runs_only_one_call_without_discovery_or_benchmark(self):
        state = {}
        with patch.object(router, 'complete', side_effect=lambda c, *args: answer(c)) as complete, \
             patch.object(router, 'discover_gemini_models', side_effect=AssertionError('Unneeded lookup')):
            result = router.route_completion('Source prompt', **KEYS, state=state, task='mcq')
        self.assertEqual(result.provider, 'Cerebras')
        self.assertEqual(complete.call_count, 1)
        self.assertEqual(state['last_result']['task'], 'mcq')
        self.assertNotIn('test-cerebras-key', json.dumps(state))

    def test_fast_valid_task_measurements_outrank_default_order(self):
        state = {}
        candidates = router.build_candidates(**KEYS)
        router.record_success(state, candidates[0], answer(candidates[0], elapsed=8), 'mcq')
        router.record_success(state, candidates[1], answer(candidates[1], elapsed=2), 'mcq')
        with patch.object(router, 'complete', side_effect=lambda c, *args: answer(c)) as complete:
            result = router.route_completion('Source prompt', **KEYS, state=state, task='mcq')
        self.assertEqual(result.provider, 'Groq')
        self.assertEqual(complete.call_count, 1)

    def test_task_observations_outrank_tiny_probe_and_model_eligibility_is_preserved(self):
        state = {}
        candidates = router.build_candidates(**KEYS)
        cerebras, groq = candidates[:2]
        router.record_success(state, groq, answer(groq, elapsed=.1), 'mcq')
        router.record_success(state, cerebras, answer(cerebras, elapsed=3), 'topic')
        study = router.ranked_candidates(router.build_candidates(**KEYS, task='topic'), state, 'topic')
        self.assertEqual(study[0].provider, 'cerebras')
        self.assertTrue(all(c.model != 'openai/gpt-oss-20b' for c in study))

    def test_invalid_fast_output_never_wins_and_valid_fallback_is_learned(self):
        state = {}
        def respond(candidate, *args):
            return answer(candidate, text='broken' if candidate.provider == 'cerebras' else 'valid', elapsed=.1)
        with patch.object(router, 'complete', side_effect=respond) as complete:
            first = router.route_completion('Source prompt', **KEYS, state=state, task='mcq', validator=lambda t: t == 'valid')
            again = router.route_completion('Source prompt', **KEYS, state=state, task='mcq', validator=lambda t: t == 'valid')
        self.assertEqual((first.provider, again.provider), ('Groq', 'Groq'))
        self.assertEqual(complete.call_count, 3)
        self.assertTrue(all('groq:' in candidate_id for candidate_id in state['stats']))

    def test_validator_exception_is_an_invalid_response_and_can_fall_back(self):
        def validate(text):
            if text == 'broken':
                raise ValueError('Malformed JSON')
            return True
        with patch.object(router, 'complete', side_effect=lambda c, *args: answer(c, 'broken' if c.provider == 'cerebras' else 'valid')):
            result = router.route_completion('Prompt', **KEYS, validator=validate)
        self.assertEqual(result.provider, 'Groq')

    def test_auth_cooldown_applies_to_every_provider_and_new_keys_can_recover(self):
        for provider in ('groq', 'cerebras', 'gemini'):
            with self.subTest(provider=provider):
                configured = dict(groq_keys=['bad'] if provider == 'groq' else [],
                                  cerebras_key='bad' if provider == 'cerebras' else '',
                                  gemini_key='bad' if provider == 'gemini' else '')
                state = {}
                with patch.object(router, 'discover_gemini_models', return_value=['gemini-3.5-flash-lite']), \
                     patch.object(router, 'complete', side_effect=ProviderError('Auth', kind='auth')) as complete:
                    for _ in range(2):
                        with self.assertRaises(RuntimeError):
                            router.route_completion('Prompt', **configured, state=state)
                self.assertEqual(complete.call_count, 1)
                candidate = router.build_candidates(**configured)[0]
                self.assertFalse(router.is_ready(state, candidate, 'topic'))
                new_config = {k: ['new'] if k == 'groq_keys' and v else 'new' if v else v for k, v in configured.items()}
                self.assertTrue(router.is_ready(state, router.build_candidates(**new_config)[0], 'topic'))

    def test_retry_after_is_honored_and_model_failure_only_skips_that_model(self):
        for candidate in router.build_candidates(**KEYS)[:3]:
            state = {}
            router.record_failure(state, candidate, ProviderError('Quota', kind='rate_limit', retry_after=240), now=100)
            self.assertFalse(router.is_ready(state, candidate, 'mcq', now=339))
            self.assertTrue(router.is_ready(state, candidate, 'mcq', now=340))
        candidates = router.build_candidates(cerebras_key='key')
        state = {}
        router.record_failure(state, candidates[0], ProviderError('Model', kind='model'), now=100)
        self.assertFalse(router.is_ready(state, candidates[0], 'mcq', now=101))
        self.assertTrue(router.is_ready(state, candidates[1], 'mcq', now=101))

    def test_timeout_cools_service_and_skips_its_other_keys_or_models(self):
        state = {}
        def respond(candidate, *args):
            if candidate.provider == 'cerebras':
                raise ProviderError('Timed out', kind='timeout')
            return answer(candidate)
        with patch.object(router, 'complete', side_effect=respond) as complete:
            result = router.route_completion('Prompt', **KEYS, state=state)
            again = router.route_completion('Prompt', **KEYS, state=state)
        self.assertEqual((result.provider, again.provider), ('Groq', 'Groq'))
        self.assertEqual([call.args[0].provider for call in complete.call_args_list], ['cerebras', 'groq', 'groq'])

    def test_deadline_clamps_attempt_budgets_and_stops_new_attempts(self):
        clock = [0]
        budgets = []
        def fail(candidate, prompt, tokens, temperature, budget):
            budgets.append(budget)
            clock[0] += budget
            raise ProviderError('Unavailable', kind='timeout')
        with patch.object(router.time, 'monotonic', side_effect=lambda: clock[0]), \
             patch.object(router, 'complete', side_effect=fail), \
             patch.object(router, 'discover_gemini_models', side_effect=AssertionError('No remaining budget')):
            with self.assertRaises(RuntimeError):
                router.route_completion('Prompt', **KEYS, deadline=30)
        self.assertEqual(budgets, [25, 5])

    def test_gemini_discovery_is_lazy_cached_and_auth_errors_skip_completions(self):
        state = {}
        with patch.object(router, 'discover_gemini_models', return_value=['gemini-3.5-flash-lite']) as discover, \
             patch.object(router, 'complete', side_effect=lambda c, *args: answer(c)) as complete:
            for _ in range(2):
                self.assertEqual(router.route_completion('Prompt', gemini_key='key', state=state).provider, 'Gemini')
        self.assertEqual(discover.call_count, 1)
        self.assertEqual(complete.call_count, 2)
        state = {}
        with patch.object(router, 'discover_gemini_models', side_effect=ProviderError('Auth', kind='auth')) as discover, \
             patch.object(router, 'complete', side_effect=AssertionError('Auth already failed')):
            for _ in range(2):
                with self.assertRaises(RuntimeError):
                    router.route_completion('Prompt', gemini_key='key', state=state)
        self.assertEqual(discover.call_count, 1)

    def test_failed_discovery_uses_current_defaults_without_repeating_lookup(self):
        state = {}
        with patch.object(router, 'discover_gemini_models', side_effect=ProviderError('Lookup timeout', kind='timeout')) as discover, \
             patch.object(router, 'complete', side_effect=lambda c, *args: answer(c)):
            for _ in range(2):
                self.assertEqual(router.route_completion('Prompt', gemini_key='key', state=state).model, 'gemini-3.5-flash-lite')
        self.assertEqual(discover.call_count, 1)

    def test_profile_is_local_sanitized_and_stale_or_malformed_profiles_are_ignored(self):
        candidate = router.build_candidates(groq_keys=['test-key'])[0]
        state = {}
        router.record_success(state, candidate, answer(candidate))
        profile = dict(schema=1, created_at=router.time.time(), **state)
        with patch.object(Path, 'read_text', return_value=json.dumps(profile)) as read:
            loaded = router.load_speed_profile('unused-profile.json')
            self.assertEqual(loaded['stats'], state['stats'])
            profile['created_at'] -= 3700
            read.return_value = json.dumps(profile)
            self.assertEqual(router.load_speed_profile('unused-profile.json'), {})
            read.return_value = '{broken'
            self.assertEqual(router.load_speed_profile('unused-profile.json'), {})


if __name__ == '__main__':
    unittest.main()
