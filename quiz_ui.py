"""Simple MCQ practice with immediate, source-backed answer feedback."""

from html import escape

import streamlit as st


def _clear_answer_widgets():
    for key in list(st.session_state):
        if key.startswith("ans_") and key[4:].isdigit():
            del st.session_state[key]


def _save_answers(mcqs, state):
    # Keep answers independently of radio widgets: changing the app's view can
    # remove those widgets and their Streamlit state until the user returns.
    for index, question in enumerate(mcqs):
        key = f"ans_{index}"
        if key not in st.session_state:
            continue
        answer = st.session_state[key]
        if answer in question["options"]:
            state["answers"][index] = answer
        else:
            state["answers"].pop(index, None)


def _render_answer_feedback(question, chosen):
    if chosen is None:
        return
    correct = question["options"][question["answer_index"]]
    right = chosen == correct
    explanation = question.get("explanation") or "No explanation was provided for this question."
    message = (
        f"{'Correct' if right else 'Incorrect'}. Correct answer: {correct}\n\n"
        f"Explanation: {explanation}"
    )
    (st.success if right else st.error)(message)
    reference = question.get("page")
    if reference:
        st.caption(f"Reference: {reference}")


def render_mcqs(mcqs, set_id, topic=""):
    """Render every MCQ with immediate feedback from its existing payload.

    Each question contains question, options, answer_index, and optionally
    explanation and page. Change set_id when generating a new set, and retain
    it when appending questions. No generation or provider calls occur here.
    """
    if not mcqs:
        return

    set_id = str(set_id)
    state = st.session_state.get("_mcq_answer_state")
    if state is None or state["set_id"] != set_id:
        _clear_answer_widgets()
        state = {"set_id": set_id, "answers": {}}
        st.session_state["_mcq_answer_state"] = state

    _save_answers(mcqs, state)
    state["answers"] = {
        index: answer for index, answer in state["answers"].items()
        if index < len(mcqs) and answer in mcqs[index]["options"]
    }
    _render_mcqs_fragment(mcqs, state, topic)


@st.fragment
def _render_mcqs_fragment(mcqs, state, topic):
    # A choice saves immediately and reruns only this list, leaving the app's
    # study controls and generation services untouched.
    _save_answers(mcqs, state)
    title = "MCQs" + (f" \u00b7 {topic}" if topic else "")
    st.markdown(f"### {title}")
    st.caption("Choose an option to see the correct answer and explanation.")

    for index, question in enumerate(mcqs):
        key = f"ans_{index}"
        if key not in st.session_state or st.session_state[key] not in [None, *question["options"]]:
            st.session_state[key] = state["answers"].get(index)
        # Keep the established container key so the app theme owns its card
        # background, border, and spacing without a second native border.
        with st.container(border=False, key=f"quiz_question_{index}"):
            st.markdown(
                f'<div class="quiz-question-heading"><div class="mcq-num">QUESTION {index + 1}</div>'
                f'<div class="mcq-q">{escape(question["question"])}</div></div>',
                unsafe_allow_html=True,
            )
            st.radio(f"Answer for question {index + 1}", question["options"],
                     key=key, index=None, label_visibility="collapsed",
                     format_func=lambda option, options=question["options"]: f"{'ABCD'[options.index(option)]}. {option}",
                     on_change=_save_answers, args=(mcqs, state))
            _render_answer_feedback(question, state["answers"].get(index))
