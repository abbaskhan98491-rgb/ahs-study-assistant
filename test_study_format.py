import unittest

from study_format import build_study_instructions, classify_study_request


class StudyFormatTests(unittest.TestCase):
    def test_bare_topics_get_full_teaching(self):
        for question in ("Neuron", "nervous system", "Explain glycolysis", "What is a neuron?",
                         "Type II hypersensitivity"):
            with self.subTest(question=question):
                self.assertEqual(classify_study_request(question), "topic")
                self.assertIn("FULL TOPIC EXPLANATION", build_study_instructions(question))

    def test_explicit_definitions_stay_short(self):
        for question in ("Define neuron", "Please define a paragraph", "definition of metabolism",
                         "Neuron definition", "Neuron ki definition", "Neuron: Define neuron",
                         "What is the definition of synapse?", "Give the definition of a clause",
                         "Can you define neuron?", "Could you please define neuron?",
                         "Please tell me the definition of neuron"):
            with self.subTest(question=question):
                self.assertEqual(classify_study_request(question), "definition")
                instructions = build_study_instructions(question)
                self.assertIn("one to three sentences", instructions)
                self.assertNotIn("400-700", instructions)

    def test_mixed_requests_do_not_collapse_to_one_definition(self):
        for question in ("Explain neuron with definition, types and functions",
                         "Define neuron and explain its functions", "Define synapse with examples",
                         "Neuron: definition, types, functions", "Define neuron and describe it",
                         "Definition of synapse; explanation of transmission"):
            with self.subTest(question=question):
                self.assertEqual(classify_study_request(question), "topic")

    def test_specific_aspects_are_explained_in_scope(self):
        for question in ("Types of neurons", "Explain functions of neurons", "Steps of glycolysis",
                         "Difference between sensory and motor neurons", "Neuron: Explain structure of neuron"):
            with self.subTest(question=question):
                self.assertEqual(classify_study_request(question), "specific")
                self.assertIn("FOCUSED EXPLANATION", build_study_instructions(question))

    def test_all_intents_use_sources_and_compact_end_references(self):
        for intent in ("definition", "specific", "topic"):
            instructions = build_study_instructions("Neuron", intent)
            self.assertIn("ONLY the supplied source", instructions)
            self.assertIn("ONE short References line at the end", instructions)
            self.assertIn("Do not invent", instructions)


if __name__ == "__main__":
    unittest.main()
