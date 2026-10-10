"""Offline regression checks: no API keys, API calls, or database writes."""
import ast
from collections import Counter
import copy
import json
import os
from pathlib import Path
import re
import time
import types
import unittest

from study_utils import compact_context, parse_mcqs, friendly_error
from syllabus import SYLLABUS_DETAILS, SYLLABUS_DATA, build_study_scope
from mcq_order import balance_mcq_options
from study_format import classify_study_request, build_study_instructions


BOOK = 'English-Slides.pdf'
CONTEXT = f'[{BOOK}, page 7]\nA paragraph has a topic sentence.'


def question(**changes):
    q = dict(question='The main idea of a paragraph is expressed by its',
             options=['Topic sentence', 'Conclusion', 'Title', 'Transition'],
             answer_index=0, explanation='The topic sentence states the main idea.',
             page=f'{BOOK}, page 7')
    q.update(changes)
    return q


def core_namespace():
    tree = ast.parse(Path('app.py').read_text(encoding='utf-8'))
    functions = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            node.decorator_list = []
            functions.append(node)
        elif isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id.startswith('MCQ_RULES_')
                for target in node.targets):
            functions.append(node)
    def no_live_routing(*args, **kwargs):
        raise AssertionError('An offline integration test must mock the provider router')
    ns = dict(re=re, time=time, parse_mcqs=parse_mcqs, compact_context=compact_context,
              balance_mcq_options=balance_mcq_options,
              classify_study_request=classify_study_request,
              build_study_instructions=build_study_instructions,
              st=types.SimpleNamespace(session_state={}), TOP_K=6,
              MCQ_CONTEXT_K=45, MCQ_TOTAL=40, MCQ_BATCH=16,
              GROQ_KEYS=[], CEREBRAS_API_KEY='', GEMINI_API_KEY='',
              GROQ_MODEL='answer-model', GROQ_MCQ_MODEL='quiz-model',
              route_completion=no_live_routing, load_speed_profile=lambda: {})
    exec(compile(ast.Module(body=functions, type_ignores=[]), 'app.py', 'exec'), ns)
    return ns


class QuizParsingTests(unittest.TestCase):
    def test_memory_error_explains_local_failure(self):
        self.assertIn('paging file', friendly_error(OSError('os error 1455')))
        self.assertIn('memory', friendly_error(MemoryError()))

    def test_provider_error_does_not_expose_request_details(self):
        self.assertNotIn('secret-token', friendly_error(RuntimeError('URL contains secret-token')))

    def test_truncated_json_with_braces_inside_text(self):
        q = question(explanation='A sentence may contain {braces} and "quotes".')
        text = '```json\n[' + json.dumps(q) + ', {"question": "unfinished'
        self.assertEqual(parse_mcqs(text, BOOK, CONTEXT), [q])

    def test_bad_items_do_not_crash(self):
        cases = [None, 1, 'text', {}, question(options=[1, 2, 3, 4]),
                 question(answer_index=True), question(question=[]),
                 question(options=['Same', 'Same', 'Third', 'Fourth'])]
        self.assertEqual(parse_mcqs(json.dumps(cases), BOOK, CONTEXT), [])

    def test_wrong_source_and_invented_page_rejected(self):
        cases = [question(page='Anatomy.pdf, page 7'), question(page=f'{BOOK}, page 999')]
        self.assertEqual(parse_mcqs(json.dumps(cases), BOOK, CONTEXT), [])

    def test_negative_combining_option_rejected(self):
        q = question(question='All of the following are paragraph components EXCEPT:',
                     options=['Title', 'Topic sentence', 'Conclusion', 'Both A and B'])
        self.assertEqual(parse_mcqs(json.dumps([q]), BOOK, CONTEXT), [])

    def test_compaction_preserves_pages(self):
        metas = [{'book': BOOK, 'page': 7}, {'book': BOOK, 'page': 7},
                 {'book': BOOK, 'page': 8}]
        result = compact_context(['First sentence. Second sentence.',
                                  'Second sentence. Third sentence.', 'Fourth sentence.'], metas)
        self.assertEqual(result.count('Second sentence.'), 1)
        self.assertIn(f'[{BOOK}, page 8]', result)
        self.assertIn('Third sentence.', result)


class CoreTests(unittest.TestCase):
    def test_study_depth_controls_prompt_context_and_budget(self):
        ns = core_namespace()
        calls = []
        ns['retrieve'] = lambda *args: (calls.append(('search', args[4])) or ['Neuron source text'],
                                       [{'book': BOOK, 'page': 7}])
        def provider(prompt, client, **kwargs):
            calls.append(('answer', prompt, kwargs['max_tokens'], kwargs.get('task'), kwargs.get('validator')))
            return 'Answer text', 'Test provider'
        ns['call_llm'] = provider
        ns['get_relevant_diagram_pages'] = lambda *args: []
        for query, intent, heading, context_count, budget in (
                ('Neuron', 'topic', 'FULL TOPIC EXPLANATION', 10, 2500),
                ('Define neuron', 'definition', 'DEFINITION ONLY', 6, 600),
                ('Types of neurons', 'specific', 'FOCUSED EXPLANATION', 6, 1800)):
            calls.clear()
            ns['answer_question'](query, 'Physiology', BOOK, None, None, None)
            self.assertEqual(calls[0], ('search', context_count))
            self.assertIn(heading, calls[1][1])
            self.assertEqual(calls[1][2], budget)
            self.assertEqual(calls[1][3], intent)
            self.assertIsNone(calls[1][4])
            self.assertIn('ONE short References line at the end', calls[1][1])

    def test_old_cached_first_answers_rebalance_without_new_ai_calls(self):
        ns = core_namespace()
        old = [question(question=f'Question {i}', options=[f'Correct{i}', f'Other{i}', f'Third{i}', f'Fourth{i}'])
               for i in range(40)]
        key = ('paragraph', 'English', BOOK, 40)
        ns['st'].session_state['quiz_cache'] = {key: (time.monotonic(), old, 'Test provider')}
        ns['retrieve'] = lambda *args: self.fail('A cache upgrade must not search or call AI')
        progress = types.SimpleNamespace(progress=lambda *args, **kwargs: None)
        result = ns['generate_all_mcqs']('paragraph', 'English', BOOK, None, None, None, progress)
        self.assertEqual(Counter(q['answer_index'] for q in result), {0: 10, 1: 10, 2: 10, 3: 10})
        for i, q in enumerate(result):
            self.assertEqual(q['options'][q['answer_index']], f'Correct{i}')
        again = ns['generate_all_mcqs']('paragraph', 'English', BOOK, None, None, None, progress)
        self.assertEqual(again, result)
        self.assertTrue(all(q['answer_index'] == 0 for q in old))

    def test_saved_choices_survive_option_order_upgrade_including_combining_options(self):
        ns = core_namespace()
        old = [question(options=['Sodium', 'Potassium', 'Both A and B', 'Calcium'], answer_index=2), question()]
        state = ns['st'].session_state
        state.update(mcqs=old, ans_0='Both A and B', ans_1='Conclusion',
                     _mcq_answer_state={'set_id': '3', 'answers': {0: 'Both A and B', 1: 'Conclusion'}})
        ns['_upgrade_mcq_option_order']()
        first = state['mcqs'][0]
        self.assertEqual(state['ans_0'], first['options'][first['answer_index']])
        self.assertIn('Sodium', state['ans_0'])
        self.assertIn('Potassium', state['ans_0'])
        self.assertEqual(state['ans_1'], 'Conclusion')
        self.assertEqual(state['_mcq_answer_state']['answers'], {0: state['ans_0'], 1: 'Conclusion'})
        snapshot = copy.deepcopy(state['mcqs'])
        ns['_upgrade_mcq_option_order']()
        self.assertEqual(state['mcqs'], snapshot)

    def test_old_space_labeled_choices_upgrade_without_changing_selected_meaning(self):
        ns = core_namespace()
        old = question(options=['A Topic sentence', 'B Conclusion', 'C Title', 'D Transition'],
                       _option_order_version=1)
        state = ns['st'].session_state
        state.update(mcqs=[old], ans_0='B Conclusion',
                     _mcq_answer_state={'set_id': '3', 'answers': {0: 'B Conclusion'}})
        ns['_upgrade_mcq_option_order']()
        self.assertEqual(state['ans_0'], 'Conclusion')
        self.assertEqual(state['_mcq_answer_state']['answers'], {0: 'Conclusion'})
        updated = state['mcqs'][0]
        self.assertEqual(updated['options'][updated['answer_index']], 'Topic sentence')
        self.assertEqual(updated['_option_order_version'], 2)

    def test_llm_wrapper_preserves_router_text_metadata_and_session_state(self):
        ns = core_namespace()
        ns.update(GROQ_KEYS=['offline-groq-key'], CEREBRAS_API_KEY='offline-cerebras-key',
                  GEMINI_API_KEY='offline-gemini-key')
        router_state = {'previous_success': 'Cerebras'}
        ns['st'].session_state['ai_router_state'] = router_state
        calls = []
        def route(prompt, **kwargs):
            calls.append((prompt, kwargs))
            kwargs['state']['successful_calls'] = kwargs['state'].get('successful_calls', 0) + 1
            return types.SimpleNamespace(text='First section\nSecond section', provider='Cerebras',
                                         model='offline-fast-model', elapsed=.12)
        ns['route_completion'] = route
        for task in ('definition', 'specific', 'topic'):
            self.assertEqual(ns['call_llm']('literal request', None, max_tokens=321,
                                           temperature=.2, task=task),
                             ('First section\nSecond section', 'Cerebras'))
            prompt, kwargs = calls[-1]
            self.assertEqual(prompt, 'literal request')
            self.assertEqual(kwargs['task'], task)
            self.assertEqual(kwargs['groq_keys'], ['offline-groq-key'])
            self.assertEqual(kwargs['cerebras_key'], 'offline-cerebras-key')
            self.assertEqual(kwargs['gemini_key'], 'offline-gemini-key')
            self.assertEqual(kwargs['max_tokens'], 321)
            self.assertEqual(kwargs['temperature'], .2)
            self.assertIsNone(kwargs['validator'])
            self.assertIsNone(kwargs['deadline'])
            self.assertIs(kwargs['state'], router_state)
            self.assertEqual(ns['st'].session_state['last_provider_model'], 'offline-fast-model')
            self.assertEqual(ns['st'].session_state['last_api_seconds'], .12)
        self.assertEqual(router_state['successful_calls'], 3)

    def test_mcq_batch_routes_with_source_and_minimum_count_validation(self):
        ns = core_namespace()
        candidates = [question(), question(question='A paragraph introduces its main idea using its')]
        raw = json.dumps(candidates)
        calls = []
        def route(prompt, **kwargs):
            calls.append((prompt, kwargs))
            self.assertEqual(kwargs['task'], 'mcq')
            validator = kwargs['validator']
            self.assertTrue(callable(validator))
            self.assertFalse(validator('Not valid JSON'))
            self.assertFalse(validator(json.dumps(candidates[:1])))
            self.assertFalse(validator(json.dumps([candidates[0], question(page='Wrong-source.pdf, page 7')])))
            self.assertFalse(validator(json.dumps([candidates[0], question(page=f'{BOOK}, page 999')])))
            self.assertTrue(validator(raw))
            return types.SimpleNamespace(text=raw, provider='Cerebras', model='offline-mcq-model', elapsed=.2)
        ns['route_completion'] = route
        result = ns['generate_mcq_batch']('paragraph', 'English', BOOK, CONTEXT, 4, [], None)
        self.assertEqual(result, candidates)
        self.assertEqual(len(calls), 1)
        self.assertIn('paragraph', calls[0][0])
        self.assertIn(CONTEXT, calls[0][0])
        self.assertEqual(ns['st'].session_state['last_provider'], 'Cerebras')
        self.assertEqual(ns['st'].session_state['last_provider_model'], 'offline-mcq-model')

    def test_study_answer_uses_validated_diagrams_and_skips_checks_without_sources(self):
        ns = core_namespace()
        literal_question = 'How does a topic sentence introduce a paragraph?'
        chunks = ['A topic sentence introduces the main idea.',
                  'A paragraph develops its topic sentence.',
                  'A paragraph structure diagram shows its main idea.']
        metas = [{'book': BOOK, 'page': page, 'has_diagram': False}
                 for page in (7, 18, 212)]
        validated_refs = [(BOOK, 212), (BOOK, 18)]
        retrieval_calls, provider_calls, diagram_calls = [], [], []
        def retrieve_sources(*args):
            retrieval_calls.append(args)
            return chunks, metas
        def answer_provider(prompt, client, **kwargs):
            provider_calls.append(prompt)
            return 'Source-backed study answer', 'Offline test provider'
        def check_diagrams(*args):
            diagram_calls.append(args)
            return validated_refs
        ns['retrieve'] = retrieve_sources
        ns['call_llm'] = answer_provider
        ns['get_relevant_diagram_pages'] = check_diagrams
        answer, refs = ns['answer_question'](literal_question, 'English', BOOK, None, None, None)
        self.assertEqual(answer, 'Source-backed study answer')
        self.assertEqual(retrieval_calls, [(literal_question, BOOK, None, None, ns['TOP_K'], ())])
        self.assertIn(f'QUESTION: {literal_question}\n', provider_calls[0])
        self.assertEqual(diagram_calls, [(literal_question, chunks, metas, BOOK)])
        self.assertEqual(refs, validated_refs)
        self.assertEqual(ns['st'].session_state['last_provider'], 'Offline test provider')

        ns['retrieve'] = lambda *args: ([], [])
        ns['call_llm'] = lambda *args, **kwargs: self.fail('No source must skip the provider')
        ns['get_relevant_diagram_pages'] = lambda *args: self.fail('No source must skip diagram checks')
        missing_answer, refs = ns['answer_question'](literal_question, 'English', BOOK, None, None, None)
        self.assertIn('Nothing on that was found in this source.', missing_answer)
        self.assertEqual(refs, [])

    def test_resuming_quiz_preserves_existing_questions_when_search_is_empty(self):
        ns = core_namespace()
        ns['retrieve'] = lambda *args: ([], [])
        existing = [question()]
        result = ns['generate_all_mcqs']('paragraph', 'English', BOOK, None, None, None,
            types.SimpleNamespace(progress=lambda *a, **kw: None), (), existing)
        self.assertEqual(result, existing)

    def test_partial_quiz_completion_keeps_questions_and_avoids_repeats(self):
        ns = core_namespace()
        ns['retrieve'] = lambda *args: (['text'], [{'book': BOOK, 'page': 7}])
        existing = [question(question=f'Concept{i} structure{i} function{i} mechanism{i}',
            options=[f'Answer{i}', f'Other{i}', f'Third{i}', f'Fourth{i}']) for i in range(30)]
        prompts = []
        def batch(topic, subject, book, context, n, avoid, client):
            prompts.append((n, list(avoid)))
            return existing[:2] + [question(question=f'Concept{i} structure{i} function{i} mechanism{i}',
                options=[f'Answer{i}', f'Other{i}', f'Third{i}', f'Fourth{i}']) for i in range(30, 42)]
        ns['generate_mcq_batch'] = batch
        result = ns['generate_all_mcqs']('paragraph', 'English', BOOK, None, None, None,
            types.SimpleNamespace(progress=lambda *a, **kw: None), (), existing)
        self.assertEqual(len(result), 40)
        self.assertEqual(result[:30], existing)
        self.assertEqual(len(prompts[0][1]), 30)

    def test_invalid_batch_tries_another_context_without_stopping_quiz(self):
        ns = core_namespace()
        ns['retrieve'] = lambda *args: (['text'], [{'book': BOOK, 'page': 7}])
        calls = []
        def batch(*args):
            calls.append(1)
            if len(calls) == 1:
                ns['st'].session_state['mcq_last_error'] = 'invalid JSON'
                ns['st'].session_state['mcq_last_error_kind'] = 'validation'
                return []
            start = (len(calls) - 2) * 18
            return [question(question=f'Concept{i} structure{i} function{i} mechanism{i}',
                options=[f'Answer{i}', f'Other{i}', f'Third{i}', f'Fourth{i}'])
                for i in range(start, start + args[4])]
        ns['generate_mcq_batch'] = batch
        result = ns['generate_all_mcqs']('paragraph', 'English', BOOK, None, None, None,
            types.SimpleNamespace(progress=lambda *a, **kw: None))
        self.assertEqual(len(result), 40)
        self.assertEqual(len(calls), 4)

    def test_unit_topic_and_subtopic_scopes_preserve_coverage(self):
        topic = SYLLABUS_DETAILS['Physiology']['Nervous System']['Neuron']
        self.assertEqual(len(topic), 3)
        request, terms = build_study_scope('Physiology', 'Nervous System', 'Neuron')
        self.assertEqual(len(terms), 3)
        self.assertIn('Explain the Structure of neuron', request)
        request, terms = build_study_scope('Physiology', 'Nervous System', 'Neuron', topic[0]['text'])
        self.assertEqual(len(terms), 1)
        self.assertNotIn('Explain the Structure of neuron', request)
        request, terms = build_study_scope('Physiology', 'Nervous System')
        self.assertEqual(len(terms), len(SYLLABUS_DETAILS['Physiology']['Nervous System']))
        self.assertIn('Physiology of pain', request)
        for subject, counts in SYLLABUS_DATA['row_counts'].items():
            rows = [row for topics in SYLLABUS_DETAILS[subject].values()
                    for outcomes in topics.values() for row in outcomes]
            self.assertEqual(len(rows), counts['cognitive'] + counts['practical'])
            self.assertTrue(all(row['pdf_page'] < 37 for row in rows))

    def test_unit_retrieval_balances_and_deduplicates_one_batched_search(self):
        ns = core_namespace()
        calls = []
        class Model:
            def encode(self, terms):
                calls.append(terms)
                return types.SimpleNamespace(tolist=lambda: [[0.1], [0.2]])
        class Collection:
            def query(self, **args):
                self.args = args
                return {'documents': [['shared', 'neuron'], ['shared', 'synapse']],
                        'metadatas': [[{'book': BOOK, 'page': 1}, {'book': BOOK, 'page': 2}],
                                      [{'book': BOOK, 'page': 1}, {'book': BOOK, 'page': 3}]]}
        collection = Collection()
        chunks, _ = ns['retrieve']('whole unit', BOOK, Model(), collection, 6, ('neuron', 'synapse'))
        self.assertEqual(chunks, ['shared', 'neuron', 'synapse'])
        self.assertEqual(calls, [['neuron', 'synapse']])
        self.assertEqual(collection.args['where'], {'book': BOOK})

    def test_full_paper_keeps_valid_extras_and_uses_three_requests(self):
        ns = core_namespace()
        ns['retrieve'] = lambda *args: ([f'Source passage {i}.' for i in range(45)],
            [{'book': BOOK, 'page': i + 1} for i in range(45)])
        contexts = []
        request_deadlines = []
        def batch(topic, subject, book, context, n, avoid, client):
            contexts.append(context)
            request_deadlines.append(ns['st'].session_state.get('mcq_request_deadline'))
            start = (len(contexts) - 1) * 18
            return [question(question=f'Concept{i} structure{i} function{i} mechanism{i}',
                             options=[f'Answer{i}', f'Other{i}', f'Third{i}', f'Fourth{i}'])
                    for i in range(start, start + n)]
        ns['generate_mcq_batch'] = batch
        result = ns['generate_all_mcqs']('paragraph', 'English', BOOK, None, None, None,
            types.SimpleNamespace(progress=lambda *a, **kw: None))
        self.assertEqual(len(result), 40)
        self.assertEqual([c.count(f'[{BOOK}, page ') for c in contexts], [15, 15, 15])
        self.assertEqual(len({q['question'] for q in result}), 40)
        self.assertEqual(Counter(q['answer_index'] for q in result), {0: 10, 1: 10, 2: 10, 3: 10})
        self.assertTrue(all(isinstance(deadline, (int, float)) for deadline in request_deadlines))
        self.assertEqual(len(set(request_deadlines)), 1)
        self.assertNotIn('mcq_request_deadline', ns['st'].session_state)
        # Same topic returns immediately without search or another provider call.
        ns['retrieve'] = lambda *args: self.fail('cached quiz must not search')
        again = ns['generate_all_mcqs'](' PARAGRAPH ', 'English', BOOK, None, None, None,
            types.SimpleNamespace(progress=lambda *a, **kw: None))
        self.assertEqual(again, result)
        self.assertEqual(len(contexts), 3)

    def test_search_is_filtered_to_selected_file(self):
        ns = core_namespace()
        captured = {}
        class Model:
            def encode(self, questions):
                return types.SimpleNamespace(tolist=lambda: [[0.1]])
        class Collection:
            def query(self, **kwargs):
                captured.update(kwargs)
                return {'documents': [['text']], 'metadatas': [[{'book': BOOK, 'page': 7}]]}
        ns['retrieve']('paragraph', BOOK, Model(), Collection(), 6)
        self.assertEqual(captured['where'], {'book': BOOK})
        self.assertEqual(captured['n_results'], 6)

    def test_provider_failure_ends_quiz_without_repeated_batches(self):
        ns = core_namespace()
        ns['retrieve'] = lambda *args: (['text'], [{'book': BOOK, 'page': 7}])
        calls = []
        def failed(*args):
            calls.append(1)
            ns['st'].session_state['mcq_last_error'] = 'quota'
            return []
        ns['generate_mcq_batch'] = failed
        progress = types.SimpleNamespace(progress=lambda *a, **kw: None)
        self.assertEqual(ns['generate_all_mcqs']('paragraph', 'English', BOOK, None, None, None, progress), [])
        self.assertEqual(len(calls), 1)
        self.assertNotIn('mcq_request_deadline', ns['st'].session_state)

    def test_repeat_filter_keeps_one_copy(self):
        ns = core_namespace()
        ns['retrieve'] = lambda *args: (['text'], [{'book': BOOK, 'page': 7}])
        calls = []
        def batch(*args):
            calls.append(1)
            return [question(), copy.deepcopy(question())]
        ns['generate_mcq_batch'] = batch
        result = ns['generate_all_mcqs']('paragraph', 'English', BOOK, None, None, None,
                                         types.SimpleNamespace(progress=lambda *a, **kw: None))
        self.assertEqual(len(result), 1)
        self.assertLessEqual(len(calls), 10)

    def test_llm_wrapper_defaults_to_topic_and_mcq_task_uses_request_deadline(self):
        ns = core_namespace()
        ns['st'].session_state['mcq_request_deadline'] = time.monotonic() + 150
        calls = []
        def route(prompt, **kwargs):
            calls.append(kwargs)
            return types.SimpleNamespace(text='Offline answer', provider='Groq', model='offline-model', elapsed=.3)
        ns['route_completion'] = route
        self.assertEqual(ns['call_llm']('prompt', None), ('Offline answer', 'Groq'))
        self.assertEqual(calls[-1]['task'], 'topic')
        self.assertIsNone(calls[-1]['deadline'])
        validator = lambda text: text == 'Offline answer'
        ns['call_llm']('prompt', None, model=ns['GROQ_MCQ_MODEL'], task='topic', validator=validator)
        self.assertEqual(calls[-1]['task'], 'mcq')
        self.assertEqual(calls[-1]['deadline'], ns['st'].session_state['mcq_request_deadline'])
        self.assertIs(calls[-1]['validator'], validator)
        self.assertIs(calls[0]['state'], calls[1]['state'])


class InterfaceTests(unittest.TestCase):
    def app(self):
        from streamlit.testing.v1 import AppTest
        source = Path('app.py').read_text(encoding='utf-8')
        # Replace only external services; execute the actual UI and widget code.
        source = source.replace('import chromadb', '')
        source = source.replace('from sentence_transformers import SentenceTransformer', '')
        source = source.replace('from groq import Groq', 'Groq = lambda **kwargs: None')
        source = source.replace('GROQ_KEYS = _collect_groq_keys()', 'GROQ_KEYS = []')
        source = source.replace('CEREBRAS_API_KEY = _one_key("CEREBRAS_API_KEY")', 'CEREBRAS_API_KEY = ""')
        source = source.replace('GEMINI_API_KEY = _one_key("GEMINI_API_KEY")', 'GEMINI_API_KEY = ""')
        source = source.replace('if not (GROQ_KEYS or CEREBRAS_API_KEY or GEMINI_API_KEY):', 'if False:')
        source = source.replace('# ==================== UI ====================',
            'def load_model():\n    st.session_state["test_model_loads"] = st.session_state.get("test_model_loads", 0) + 1\n    return None\n\n'
            'def load_collection():\n    st.session_state["test_collection_loads"] = st.session_state.get("test_collection_loads", 0) + 1\n    return None\n\n'
            'def answer_question(*args):\n    st.session_state["test_request"] = args[0]\n    st.session_state["test_focus"] = args[6] if len(args) > 6 else ()\n    return "Offline study answer", [("English-Slides.pdf", 7)]\n\n'
            'def render_page(*args):\n    st.session_state["render_calls"] = st.session_state.get("render_calls", 0) + 1\n    return None\n\n'
            'def generate_all_mcqs(*args):\n    st.session_state["test_quiz_request"] = args[0]\n    return ' + repr([question()]) + '\n\n'
            '# ==================== UI ====================')
        # Python 3.14 TemporaryDirectory permissions can fail under Windows sandboxing.
        test_path = Path(f'tmp/ui_regression_{os.getpid()}_{self._testMethodName}.py')
        test_path.parent.mkdir(exist_ok=True)
        test_path.write_text(source, encoding='utf-8')
        self.addCleanup(test_path.unlink, missing_ok=True)
        at = AppTest.from_file(str(test_path.resolve()), default_timeout=20).run()
        self.assertEqual(len(at.exception), 0)
        return at

    def test_initial_controls_are_ready_without_loading_search_resources(self):
        at = self.app()
        self.assertEqual(at.selectbox(key='sel_subject').value, 'Physiology')
        self.assertEqual(at.radio(key='sel_source').options, ['Book', 'Slides'])
        self.assertEqual(at.radio(key='sel_source').value, 'Book')
        self.assertEqual([widget.key for widget in at.selectbox], ['sel_subject', 'topic_suggestion'])
        self.assertEqual(at.selectbox(key='topic_suggestion').label, 'Find a syllabus topic')
        self.assertIsNone(at.selectbox(key='topic_suggestion').value)
        suggestion_proto = at.selectbox(key='topic_suggestion').proto
        filter_field = suggestion_proto.DESCRIPTOR.fields_by_name['filter_mode']
        self.assertEqual(suggestion_proto.filter_mode,
                         filter_field.enum_type.values_by_name['FILTER_MODE_FUZZY'].number)
        self.assertEqual([widget.key for widget in at.radio], ['sel_source'])
        self.assertEqual(len(at.text_input), 1)
        self.assertEqual(at.text_input(key='query_text').value, '')
        self.assertEqual(at.checkbox(key='fresh_mcqs').label, 'Make fresh questions')
        self.assertEqual(at.button(key='btn_study').label, 'Topic Study')
        self.assertEqual(at.button(key='btn_mcq').label, 'Generate 40 MCQs')
        self.assertEqual(len(at.expander), 0)
        markup = '\n'.join(element.value for element in at.markdown)
        self.assertIn('<div class="landing-layout"></div>', markup)
        self.assertIn('Created by Abbas Khan', markup)
        self.assertNotIn('<div class="empty-state">', markup)
        self.assertNotIn('test_model_loads', at.session_state)
        self.assertNotIn('test_collection_loads', at.session_state)
        self.assertNotIn('test_request', at.session_state)
        at.button(key='btn_study').click().run()
        self.assertEqual(len(at.exception), 0)
        self.assertIn('Type a topic or question first.', [alert.value for alert in at.info])
        self.assertNotIn('test_model_loads', at.session_state)
        self.assertNotIn('test_collection_loads', at.session_state)
        at.text_input(key='query_text').set_value('Types of neurons').run()
        self.assertNotIn('test_model_loads', at.session_state)
        self.assertNotIn('test_collection_loads', at.session_state)
        at.button(key='btn_study').click().run()
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(at.session_state['test_model_loads'], 1)
        self.assertEqual(at.session_state['test_collection_loads'], 1)
        self.assertEqual(at.session_state['test_request'], 'Types of neurons')
        self.assertEqual(at.session_state['test_focus'], ())
        self.assertFalse(any(radio.key == 'workspace_view' for radio in at.radio))
        self.assertEqual(at.text_input(key='query_text').value, 'Types of neurons')
        self.assertEqual(at.button(key='btn_study').label, 'Topic Study')
        self.assertEqual(at.button(key='btn_mcq').label, 'Generate 40 MCQs')
        markup = '\n'.join(element.value for element in at.markdown)
        self.assertIn('<div class="results-layout"></div>', markup)
        self.assertNotIn('<div class="landing-layout"></div>', markup)
        self.assertIn('Offline study answer', markup)
        self.assertFalse(any(expander.label == 'Change your topic' for expander in at.expander))

    def test_syllabus_suggestions_fill_topics_but_custom_question_takes_precedence(self):
        at = self.app()
        suggestion = at.selectbox(key='topic_suggestion')
        suggestion.select_index(suggestion.options.index('Neuron')).run()
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(at.text_input(key='query_text').value, 'Neuron')
        self.assertNotIn('test_model_loads', at.session_state)
        self.assertNotIn('test_collection_loads', at.session_state)
        self.assertNotIn('test_request', at.session_state)
        self.assertNotIn('test_quiz_request', at.session_state)
        self.assertNotIn('render_calls', at.session_state)

        at.radio(key='sel_source').set_value('Slides').run()
        self.assertEqual(at.text_input(key='query_text').value, 'Neuron')
        self.assertEqual(at.selectbox(key='topic_suggestion').value, 'Neuron')
        self.assertNotIn('test_model_loads', at.session_state)
        suggestion = at.selectbox(key='topic_suggestion')
        structure = next(label for label in suggestion.options
                         if label.startswith('Neuron') and 'structure' in label.casefold())
        suggestion.select_index(suggestion.options.index(structure)).run()
        selected_query = at.text_input(key='query_text').value
        self.assertTrue(selected_query.startswith('Neuron:'))
        self.assertIn('structure of neuron', selected_query.casefold())

        custom_question = 'What is the function of a neuron axon?'
        at.text_input(key='query_text').set_value(custom_question).run()
        self.assertIsNone(at.selectbox(key='topic_suggestion').value)
        self.assertNotIn('test_model_loads', at.session_state)
        at.button(key='btn_study').click().run()
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(at.session_state['test_request'], custom_question)
        self.assertEqual(at.session_state['test_focus'], ())
        self.assertEqual(at.session_state['study_result'][0], 'Physiology-Slides.pdf')
        self.assertNotIn('render_calls', at.session_state)
        at.button(key='load_source_page').click().run()
        self.assertEqual(at.session_state['render_calls'], 1)
        at.button(key='btn_mcq').click().run()
        self.assertEqual(at.session_state['test_quiz_request'], custom_question)

        at.selectbox(key='sel_subject').select('English').run()
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(at.text_input(key='query_text').value, '')
        self.assertIsNone(at.selectbox(key='topic_suggestion').value)
        self.assertNotIn('Neuron', at.selectbox(key='topic_suggestion').options)
        self.assertFalse(any(widget.label in {'Unit', 'Coverage', 'Topic', 'Focus on'}
                             for widget in at.selectbox))

    def test_free_text_notes_theme_and_mcq_feedback(self):
        at = self.app()
        self.assertNotIn('Islamic Studies', at.selectbox(key='sel_subject').options)
        at.selectbox(key='sel_subject').select('English').run()
        self.assertEqual(at.radio(key='sel_source').value, 'Slides')
        at.text_input(key='query_text').set_value('What is a paragraph topic sentence?').run()
        at.button(key='btn_study').click().run()
        self.assertEqual(at.session_state['test_request'], 'What is a paragraph topic sentence?')
        self.assertEqual(at.session_state['test_focus'], ())
        self.assertIn('Offline study answer', [m.value for m in at.markdown])
        self.assertNotIn('render_calls', at.session_state)
        at.button(key='load_source_page').click().run()
        self.assertEqual(at.session_state['render_calls'], 1)
        at.toggle(key='dark_toggle').set_value(True).run()
        self.assertIn('Offline study answer', [m.value for m in at.markdown])
        self.assertTrue(at.toggle(key='dark_toggle').value)
        self.assertEqual(at.selectbox(key='sel_subject').value, 'English')
        at.button(key='btn_mcq').click().run()
        self.assertEqual(at.session_state['test_quiz_request'], 'What is a paragraph topic sentence?')
        self.assertIsNone(at.radio(key='ans_0').value)
        labels = {button.label for button in at.button}
        self.assertFalse(labels & {'Submit & See Score', 'Previous 5', 'Next 5', 'Finish anyway'})
        at.radio(key='ans_0').set_value('Topic sentence').run()
        self.assertTrue(any('Correct' in alert.value and 'Explanation:' in alert.value for alert in at.success))
        self.assertEqual(len(at.exception), 0)
        at.toggle(key='dark_toggle').set_value(False).run()
        self.assertEqual(at.radio(key='ans_0').value, 'Topic sentence')
        self.assertTrue(any('Explanation:' in alert.value for alert in at.success))
        at.button(key='btn_mcq').click().run()
        self.assertIsNone(at.radio(key='ans_0').value)
        at.selectbox(key='sel_subject').select('Physiology').run()
        self.assertFalse(any(radio.key == 'ans_0' for radio in at.radio))
        self.assertEqual(at.text_input(key='query_text').value, '')
        at.text_input(key='query_text').set_value('Explain neuron structure').run()
        at.button(key='btn_study').click().run()
        self.assertEqual(at.session_state['test_request'], 'Explain neuron structure')
        self.assertEqual(at.session_state['test_focus'], ())
        self.assertEqual(len(at.exception), 0)


if __name__ == '__main__':
    unittest.main()
