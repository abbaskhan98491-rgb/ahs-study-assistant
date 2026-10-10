"""Match study answer depth to the student's actual request."""

import re


def classify_study_request(question):
    text = " ".join(str(question).casefold().split()).strip(" .?!")
    # Suggestions can prefix a learning outcome with its parent topic.
    request = text.rsplit(":", 1)[-1].strip()
    request = re.sub(r"^(?:(?:can|could|would)\s+you\s+|please\s+|just\s+|only\s+|sirf\s+)+", "", request)
    definition = bool(
        re.match(r"^(?:define\b|definition\b|(?:give|write|state|provide|tell\s+me)\s+(?:the\s+)?definition\b)", request)
        or re.search(r"\bdefinition(?:\s+(?:only|please|chahiye|chayi|batao))?$", request)
        or re.match(r"^what\s+is\s+(?:the\s+)?definition\b", request)
    )
    mixed = bool(re.search(
        r"(?:\b(?:and|with|including|also|aur)\b|[,;]).*\b(?:explain|explanation|describe|types?|functions?|structure|steps?|examples?|mechanism)\b",
        request,
    ))
    if definition and not mixed:
        return "definition"
    if mixed:
        return "topic"
    aspect = re.sub(r"^(?:explain|describe|list|discuss|tell\s+me|what\s+(?:are|is))\s+", "", request)
    if re.match(r"^(?:types\b|type\s+of\b|(?:functions?|structure|steps?|stages?|classification|mechanism|relations?|causes?|uses?|features?|advantages?|disadvantages?)\b)", aspect):
        return "specific"
    if re.match(r"^(?:difference|differences|compare|comparison|differentiate|distinguish)\b", aspect):
        return "specific"
    if re.match(r"^how\s+(?:does|do|is|are|can)\b", request):
        return "specific"
    return "topic"


def build_study_instructions(question, intent=None):
    intent = intent or classify_study_request(question)
    common = """Use ONLY the supplied source passages. Do not invent missing facts or examples.
Use clear, simple English and explain medical terms when the source permits it.
Do not put the book filename or a page reference after every sentence/bullet.
Put ONE short References line at the end with the source's PDF page numbers.
The explanation is the main answer; references must not replace teaching."""
    if intent == "definition":
        depth = """DEFINITION ONLY:
Give a direct, precise definition in one to three sentences.
Do not add types, functions, mechanisms, examples, long introductions or revision notes.
Do not add section headings. If the source cannot define this term, say so briefly."""
    elif intent == "specific":
        depth = """FOCUSED EXPLANATION:
Answer the exact aspect or comparison requested and explain it properly.
For types/functions, explain each item rather than giving unexplained names.
For steps/mechanisms, explain the sequence and what happens at each stage.
For a comparison, use clear paired points or a small table.
Use short paragraphs and useful headings/lists; avoid unrelated parts of the topic."""
    else:
        depth = """FULL TOPIC EXPLANATION:
The student wants to learn the complete topic, not a one-line definition or a list of references.
Begin with what it means in simple words, then teach the important source-supported details.
Use clear headings and short paragraphs. Cover structure/components, types, functions,
how it works and examples/clinical relevance where the supplied passages support them.
Explain each point and how the ideas connect; do not just list technical names.
For a broad topic with substantial source material, aim for about 400-700 words.
For a small topic use the detail the source supports; never pad with invented facts.
Finish with a short recap of the main ideas. Mention any material coverage gap briefly."""
    return depth + "\n\n" + common
