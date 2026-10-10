"""Fake-HTTP tests for request bounds, model settings, parsing, and privacy."""

from datetime import datetime, timezone
from email.utils import format_datetime
import runpy
import unittest
from unittest.mock import Mock, patch

import requests

import provider_transport as transport


KEY = 'dummy-test-secret-never-read-from-environment'


def candidate(provider='groq', model='openai/gpt-oss-20b'):
    return transport.Candidate('public-test-id', provider, model, KEY, provider.title())


def response(body=None, status=200, headers=None):
    result = Mock(status_code=status, headers=headers or {})
    result.json.return_value = body
    return result


def chat(text='Final answer', finish='stop'):
    return {'choices': [{'finish_reason': finish, 'message': {'content': text, 'reasoning': 'Private thinking'}}],
            'usage': {'completion_tokens': 17}}


def gemini(parts=None, finish='STOP'):
    return {'candidates': [{'finishReason': finish, 'content': {'parts': parts or [{'text': 'Final answer'}]}}],
            'usageMetadata': {'candidatesTokenCount': 11}}


def model(name, methods=None, **extra):
    return {'name': 'models/' + name, 'supportedGenerationMethods': methods or ['generateContent'], **extra}


class TransportTests(unittest.TestCase):
    def run_completion(self, item=None, body=None, **kwargs):
        with patch.object(transport.requests, 'post', return_value=response(body or chat())) as post:
            result = transport.complete(item or candidate(), 'Synthetic prompt', 400, 0, kwargs.get('timeout', 10))
        self.assertEqual(post.call_count, 1)
        return result, post.call_args

    def assert_private_error(self, body=None, status=200, headers=None, exception=None, kind='invalid'):
        with patch.object(transport.requests, 'post', return_value=response(body, status, headers),
                          side_effect=exception) as post:
            with self.assertRaises(transport.ProviderError) as caught:
                transport.complete(candidate(), 'Synthetic prompt', 400, 0, 10)
        error = caught.exception
        self.assertEqual(error.kind, kind)
        self.assertNotIn(KEY, str(error))
        self.assertNotIn(KEY, repr(error))
        self.assertNotIn('http', str(error))
        self.assertEqual(post.call_count, 1)
        return error

    def test_candidate_repr_and_import_have_no_credential_or_network_side_effects(self):
        self.assertNotIn(KEY, repr(candidate()))
        with patch.object(transport.requests, 'post', side_effect=AssertionError('Unexpected POST')), \
                patch.object(transport.requests, 'get', side_effect=AssertionError('Unexpected GET')):
            runpy.run_path('provider_transport.py')

    def test_groq_single_request_low_reasoning_and_bounded_timeout(self):
        result, call = self.run_completion()
        self.assertEqual(result.text, 'Final answer')
        self.assertEqual(result.provider, 'Groq')
        self.assertEqual(result.model, 'openai/gpt-oss-20b')
        self.assertEqual(result.output_tokens, 17)
        self.assertGreaterEqual(result.elapsed, 0)
        self.assertNotIn(KEY, call.args[0])
        self.assertEqual(call.kwargs['headers']['Authorization'], 'Bearer ' + KEY)
        self.assertFalse(call.kwargs['allow_redirects'])
        connect, read = call.kwargs['timeout']
        self.assertLessEqual(connect, 2)
        self.assertLessEqual(connect + read, 10)
        self.assertGreater(read, 0)
        self.assertEqual(call.kwargs['json']['reasoning_effort'], 'low')
        self.assertEqual(call.kwargs['json']['max_completion_tokens'], 400)
        self.assertNotIn('max_tokens', call.kwargs['json'])

    def test_supported_cerebras_models_use_low_reasoning_only(self):
        for name in ('gpt-oss-120b', 'qwen-3.8-27b'):
            with self.subTest(model=name):
                result, call = self.run_completion(candidate('cerebras', name))
                self.assertEqual(result.provider, 'Cerebras')
                self.assertEqual(call.kwargs['json']['reasoning_effort'], 'low')
        _, call = self.run_completion(candidate('groq', 'a-non-reasoning-model'))
        self.assertNotIn('reasoning_effort', call.kwargs['json'])

    def test_gemini_combines_final_parts_and_excludes_thoughts(self):
        result, call = self.run_completion(candidate('gemini', 'gemini-2.5-flash-lite'),
            gemini([{'thought': True, 'text': 'Private reasoning'}, {'text': 'First '}, {'text': 'answer.'}]))
        self.assertEqual(result.text, 'First answer.')
        self.assertEqual(result.output_tokens, 11)
        self.assertEqual(result.provider, 'Gemini')
        self.assertNotIn(KEY, call.args[0])
        self.assertEqual(call.kwargs['headers']['x-goog-api-key'], KEY)
        self.assertEqual(call.kwargs['json']['generationConfig']['thinkingConfig'], {'thinkingBudget': 0})

    def test_gemini_thinking_configuration_is_model_supported(self):
        cases = [('gemini-3.1-flash-lite', {'thinkingLevel': 'minimal'}),
                 ('gemini-3.5-flash-lite', {'thinkingLevel': 'minimal'}),
                 ('gemini-3.6-flash', {'thinkingLevel': 'minimal'}),
                 ('gemini-3.8-flash', {'thinkingLevel': 'low'}),
                 ('gemini-2.5-flash', {'thinkingBudget': 0}),
                 ('gemini-99-flash-lite', None)]
        for name, expected in cases:
            with self.subTest(model=name):
                _, call = self.run_completion(candidate('gemini', name), gemini())
                self.assertEqual(call.kwargs['json']['generationConfig'].get('thinkingConfig'), expected)

    def test_empty_malformed_truncated_and_blocked_responses_are_invalid(self):
        cases = [chat(''), chat('Partial', 'length'), chat('Blocked', 'content_filter'),
                 {'choices': 'bad'}, {'choices': [{'message': {'content': None}}]}, [],
                 {'error': {'message': KEY}}]
        for body in cases:
            with self.subTest(body=body):
                self.assert_private_error(body)
        bad = response()
        bad.json.side_effect = ValueError(KEY)
        with patch.object(transport.requests, 'post', return_value=bad):
            with self.assertRaises(transport.ProviderError) as caught:
                transport.complete(candidate(), 'Prompt', 400, 0, 10)
        self.assertEqual(caught.exception.kind, 'invalid')
        self.assertNotIn(KEY, str(caught.exception))

    def test_gemini_truncated_or_only_thought_content_is_invalid(self):
        for body in (gemini(finish='MAX_TOKENS'), gemini(finish='SAFETY'),
                     gemini([{'thought': True, 'text': KEY}]), gemini([{'text': None}])):
            with patch.object(transport.requests, 'post', return_value=response(body)):
                with self.assertRaises(transport.ProviderError) as caught:
                    transport.complete(candidate('gemini', 'gemini-2.5-flash-lite'), 'Prompt', 400, 0, 10)
            self.assertEqual(caught.exception.kind, 'invalid')
            self.assertNotIn(KEY, str(caught.exception))

    def test_http_error_categories_and_numeric_retry_after(self):
        cases = [(401, 'auth'), (403, 'auth'), (429, 'rate_limit'), (404, 'model'),
                 (410, 'model'), (408, 'timeout'), (504, 'timeout'), (503, 'unavailable'),
                 (302, 'unavailable'), (422, 'invalid')]
        for status, kind in cases:
            with self.subTest(status=status):
                error = self.assert_private_error({'error': {'message': KEY}}, status,
                                                 {'Retry-After': '7.5'}, kind=kind)
                self.assertEqual(error.status_code, status)
                self.assertEqual(error.retry_after, 7.5)
        self.assert_private_error({'error': {'code': 'model_not_found', 'message': KEY}}, 400, kind='model')

    def test_retry_after_http_date_and_invalid_values(self):
        now = datetime(2026, 10, 10, 0, 0, 0, tzinfo=timezone.utc)
        later = datetime(2026, 10, 10, 0, 0, 30, tzinfo=timezone.utc)
        with patch.object(transport, 'datetime') as clock:
            clock.now.return_value = now
            error = self.assert_private_error({}, 429, {'Retry-After': format_datetime(later)}, kind='rate_limit')
        self.assertEqual(error.retry_after, 30)
        for value in ('not-a-date', 'nan', 'inf'):
            self.assertIsNone(transport._retry_after(value))
        self.assertEqual(transport._retry_after('-1'), 0)

    def test_quota_status_sets_sanitized_one_hour_credential_cooldown(self):
        for headers, expected in (({}, 3600), ({'Retry-After': '10'}, 3600),
                                  ({'Retry-After': '7200'}, 7200), ({'Retry-After': 'not-valid'}, 3600)):
            with self.subTest(headers=headers):
                error = self.assert_private_error({'error': {'message': KEY}}, 402, headers,
                                                 kind='rate_limit')
                self.assertEqual(error.status_code, 402)
                self.assertEqual(error.retry_after, expected)
                self.assertNotIn('credit', str(error).lower())
                self.assertNotIn('payment', str(error).lower())

    def test_network_errors_are_sanitized_and_never_retried(self):
        for exception, kind in ((requests.ReadTimeout(KEY), 'timeout'),
                                (requests.ConnectTimeout(KEY), 'timeout'),
                                (requests.ConnectionError(KEY), 'unavailable')):
            self.assert_private_error(exception=exception, kind=kind)

    def test_invalid_inputs_do_not_start_network_requests(self):
        cases = [(candidate(), '', 400, 0, 10), (candidate(), 'Prompt', 0, 0, 10),
                 (candidate(), 'Prompt', 400, float('nan'), 10),
                 (candidate(), 'Prompt', 400, 0, 0)]
        with patch.object(transport.requests, 'post') as post:
            for args in cases:
                with self.assertRaises(transport.ProviderError):
                    transport.complete(*args)
            self.assertEqual(post.call_count, 0)

    def test_gemini_paginated_discovery_excludes_special_models_and_orders_stable_flash(self):
        pages = [response({'models': [model('gemini-3.8-flash'), model('gemini-2.5-flash-lite'),
                                      model('gemini-3.1-flash-lite-preview'), model('gemini-2.5-flash-image'),
                                      model('gemini-2.5-flash-tts'), model('gemini-2.5-flash-live'),
                                      model('gemini-embedding-001', ['embedContent']),
                                      model('gemini-3.5-flash-lite', outputModalities=['AUDIO'])],
                           'nextPageToken': 'next-public-page'}),
                 response({'models': [model('gemini-3.5-flash-lite'), model('gemini-3.6-flash'),
                                      model('gemini-3.8-flash'), model('gemini-2.5-pro')]})]
        with patch.object(transport.requests, 'get', side_effect=pages) as get:
            names = transport.discover_gemini_models(KEY)
        self.assertEqual(names, ['gemini-3.5-flash-lite', 'gemini-2.5-flash-lite', 'gemini-3.8-flash', 'gemini-3.6-flash'])
        self.assertEqual(get.call_count, 2)
        self.assertNotIn('pageToken', get.call_args_list[0].kwargs['params'])
        self.assertEqual(get.call_args_list[1].kwargs['params']['pageToken'], 'next-public-page')
        for call in get.call_args_list:
            self.assertNotIn(KEY, call.args[0])
            self.assertNotIn('key', call.kwargs['params'])
            self.assertLessEqual(sum(call.kwargs['timeout']), 4)

    def test_discovery_failures_are_sanitized_and_repeated_page_tokens_rejected(self):
        with patch.object(transport.requests, 'get', return_value=response({'error': {'message': KEY}}, 403)):
            with self.assertRaises(transport.ProviderError) as caught:
                transport.discover_gemini_models(KEY)
        self.assertEqual(caught.exception.kind, 'auth')
        self.assertNotIn(KEY, str(caught.exception))
        with patch.object(transport.requests, 'get', return_value=response({'models': [], 'nextPageToken': 'same'})) as get:
            with self.assertRaises(transport.ProviderError) as caught:
                transport.discover_gemini_models(KEY)
        self.assertEqual(caught.exception.kind, 'invalid')
        self.assertEqual(get.call_count, 2)


if __name__ == '__main__':
    unittest.main()
