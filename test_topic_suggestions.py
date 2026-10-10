"""Coverage and isolation checks for the local syllabus suggestion catalogue."""

import ast
import json
import runpy
import unittest
from pathlib import Path
from unittest.mock import patch

import topic_suggestions
from topic_suggestions import get_topic_suggestions


def normal(text):
    return " ".join(text.split()).casefold()


class TopicSuggestionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.subjects = json.loads(Path(__file__).with_name("syllabus_details.json").read_text(
            encoding="utf-8"))["subjects"]

    def tearDown(self):
        topic_suggestions._catalogue.cache_clear()
        topic_suggestions._load_subjects.cache_clear()

    def test_catalogue_covers_every_source_topic_and_learning_outcome(self):
        for subject, units in self.subjects.items():
            with self.subTest(subject=subject):
                choices = get_topic_suggestions(subject)
                labels = {normal(label) for label, _ in choices}
                for topics in units.values():
                    for topic, rows in topics.items():
                        topic = " ".join(topic.split())
                        # Ambiguous generic headings are represented by their
                        # distinct source outcomes rather than one misleading label.
                        self.assertTrue(normal(topic) in labels or any(
                            normal(label).startswith(normal(topic) + " · ") for label, _ in choices))
                        for row in rows:
                            text = " ".join(row["text"].split())
                            self.assertTrue(normal(text) in labels or
                                            normal(f"{topic} · {text}") in labels,
                                            (subject, topic, text))

    def test_choices_are_immutable_nonempty_and_labels_are_unique(self):
        for subject in self.subjects:
            choices = get_topic_suggestions(subject)
            self.assertIsInstance(choices, tuple)
            self.assertTrue(choices)
            identities = [normal(label) for label, _ in choices]
            self.assertEqual(len(identities), len(set(identities)))
            self.assertTrue(all(isinstance(item, tuple) and len(item) == 2 and all(item)
                                for item in choices))

    def test_neuron_and_all_its_specific_outcomes_are_searchable(self):
        choices = dict(get_topic_suggestions("Physiology"))
        self.assertEqual(choices["Neuron"], "Neuron")
        for outcome in self.subjects["Physiology"]["Nervous System"]["Neuron"]:
            text = outcome["text"]
            self.assertEqual(choices[f"Neuron · {text}"], f"Neuron: {text}")
        self.assertIn("Neuron · Describe the classification of neuron and nerve fiber", choices)

    def test_subjects_do_not_leak_into_each_other(self):
        marker = {"Physiology": "Neuron", "Biochemistry": "Glycolysis",
                  "Anatomy": "Scalp", "English": "Paragraph Writing"}
        for selected, own_topic in marker.items():
            choices = dict(get_topic_suggestions(selected))
            self.assertIn(own_topic, choices)
            for other, foreign_topic in marker.items():
                if other != selected:
                    self.assertNotIn(foreign_topic, choices)

    def test_unknown_and_excluded_subjects_perform_no_file_read(self):
        with patch.object(topic_suggestions, "_load_subjects") as load:
            for subject in ("Islamiyat", "Islamic Studies", "", None, "Unknown", "../Physiology"):
                self.assertEqual(get_topic_suggestions(subject), ())
            load.assert_not_called()

    def test_subject_case_whitespace_and_catalogue_cache(self):
        first = get_topic_suggestions("Physiology")
        self.assertIs(first, get_topic_suggestions(" physiology  "))
        self.assertGreaterEqual(topic_suggestions._catalogue.cache_info().hits, 1)

    def test_generic_headings_retain_distinct_meaningful_source_contexts(self):
        choices = dict(get_topic_suggestions("Biochemistry"))
        self.assertNotIn("Definition", choices)
        self.assertNotIn("ATP calculation", choices)
        for text in ("Define metabolism", "Define nutrients and nutrition",
                     "Define clinical/ diagnostic enzymology"):
            self.assertEqual(choices[f"Definition · {text}"], f"Definition: {text}")
        self.assertTrue(any("one molecule of glucose" in label for label in choices))
        self.assertTrue(any("one fatty acid molecule" in label for label in choices))

    def test_import_is_lazy_and_only_standard_library_dependencies_are_used(self):
        module_path = Path(topic_suggestions.__file__)
        with patch.object(Path, "read_text", side_effect=AssertionError("Import read the syllabus")):
            runpy.run_path(str(module_path))
        parsed = ast.parse(module_path.read_text(encoding="utf-8"))
        imports = set()
        for node in ast.walk(parsed):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.add(node.module.split(".")[0])
        self.assertEqual(imports, {"json", "collections", "functools", "pathlib"})

    def test_one_json_read_serves_multiple_subject_catalogues(self):
        source = json.dumps({"subjects": self.subjects})
        topic_suggestions._catalogue.cache_clear()
        topic_suggestions._load_subjects.cache_clear()
        with patch.object(Path, "read_text", return_value=source) as read:
            get_topic_suggestions("Physiology")
            get_topic_suggestions("Physiology")
            get_topic_suggestions("English")
            read.assert_called_once()

    def test_whitespace_case_duplicates_are_removed_without_changing_source_words(self):
        fixture = {"Physiology": {"Ignored unit": {
            " Neuron ": [{"text": " Explain  the Structure of neuron "},
                         {"text": "explain the structure of NEURON"}],
            "neuron": [{"text": "Define Neuron."}],
            "Practice label nerve": [{"text": "Practice label nerve"}],
        }}}
        with patch.object(topic_suggestions, "_load_subjects", return_value=fixture):
            choices = get_topic_suggestions("Physiology")
        self.assertEqual(choices, (("Neuron", "Neuron"),
                                  ("Neuron · Explain the Structure of neuron",
                                   "Neuron: Explain the Structure of neuron"),
                                  ("neuron · Define Neuron.", "neuron: Define Neuron."),
                                  ("Practice label nerve", "Practice label nerve")))
        self.assertFalse(any("Ignored unit" in value for item in choices for value in item))

    def test_missing_optional_syllabus_keeps_custom_question_flow_available(self):
        with patch.object(Path, "read_text", side_effect=FileNotFoundError):
            self.assertEqual(get_topic_suggestions("Physiology"), ())


if __name__ == "__main__":
    unittest.main()
