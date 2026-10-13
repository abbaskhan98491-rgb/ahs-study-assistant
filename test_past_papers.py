"""Past-paper MCQs: the bank is clean, and only on-topic questions are picked."""

import json
from pathlib import Path
import unittest

import past_papers
from past_papers import pick_past_questions


BANK = json.loads(Path("past_papers.json").read_text(encoding="utf-8"))["questions"]


class BankTests(unittest.TestCase):
    def test_every_question_is_usable(self):
        self.assertGreater(len(BANK), 200)
        for row in BANK:
            with self.subTest(question=row["question"][:50]):
                self.assertIn(row["subject"], {"Biochemistry", "Anatomy", "Physiology", "English"})
                self.assertEqual(len(row["options"]), 4)
                self.assertEqual(len({o.strip().casefold() for o in row["options"]}), 4)
                self.assertIn(row["answer_index"], range(4))
                self.assertTrue(row["source"])

    def test_no_question_is_listed_twice(self):
        keys = [(row["subject"], " ".join(row["question"].casefold().split())) for row in BANK]
        self.assertEqual(len(keys), len(set(keys)))


class PickTests(unittest.TestCase):
    def pick(self, topic, subject, context="", limit=8):
        return pick_past_questions(topic, subject, context or topic, limit=limit)

    def test_on_topic_questions_are_picked_and_marked(self):
        got = self.pick("urea cycle", "Biochemistry")
        self.assertTrue(got)
        for q in got:
            text = (q["question"] + " " + q["options"][q["answer_index"]]).casefold()
            self.assertIn("urea", text)
            self.assertTrue(q["past_paper"])
            self.assertTrue(q["page"].startswith("Past paper: "))
            self.assertTrue(q["explanation"])

    def test_near_but_wrong_topics_are_not_picked(self):
        # "cycle" alone must not drag citric-acid-cycle questions into urea cycle.
        for q in self.pick("urea cycle", "Biochemistry"):
            self.assertNotIn("citric", q["question"].casefold())
        # "plexus" alone must not bring cervical-plexus questions to brachial plexus.
        for q in self.pick("brachial plexus", "Anatomy"):
            self.assertIn("brachial", q["question"].casefold())

    def test_subject_and_limit_are_respected(self):
        self.assertEqual(self.pick("urea cycle", "English"), [])
        self.assertLessEqual(len(self.pick("carbohydrate metabolism", "Biochemistry", limit=3)), 3)
        self.assertEqual(self.pick("glycolysis", "Biochemistry", limit=0), [])

    def test_topic_with_and_accepts_either_part(self):
        got = self.pick("phrases and clauses", "English")
        joined = " ".join(q["question"] + q["options"][q["answer_index"]] for q in got).casefold()
        self.assertIn("phrase", joined)
        self.assertIn("clause", joined)

    def test_word_forms_match(self):
        self.assertTrue(self.pick("cranial nerves", "Anatomy"))       # "Cranial nerve VI..."
        self.assertTrue(self.pick("glycolysis", "Biochemistry"))      # also "glycolytic"
        self.assertFalse(past_papers._same_word("cell", "cellulose"))

    def test_picked_questions_are_copies(self):
        first = self.pick("urea cycle", "Biochemistry")[0]
        first["options"][0] = "changed"
        self.assertNotIn("changed", self.pick("urea cycle", "Biochemistry")[0]["options"])

    def test_missing_bank_is_harmless(self):
        past_papers._bank.cache_clear()
        original = past_papers.Path
        try:
            past_papers.Path = lambda *_: Path("does-not-exist") / "x"
            self.assertEqual(pick_past_questions("urea cycle", "Biochemistry", "urea"), [])
        finally:
            past_papers.Path = original
            past_papers._bank.cache_clear()


if __name__ == "__main__":
    unittest.main()
