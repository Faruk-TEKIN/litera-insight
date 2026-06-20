from backend.app.services.assistant_safety import (
    GREETING_RESPONSE,
    REFUSAL_RESPONSE,
    evaluate_user_message_safety,
    is_refusal_response,
)


def test_simple_greeting_uses_academic_intro_response():
    decision = evaluate_user_message_safety("hi")

    assert decision.should_block is True
    assert decision.reason == "simple_greeting"
    assert decision.response == GREETING_RESPONSE
    assert decision.response.endswith("What would you like to know?")


def test_scope_question_uses_academic_intro_response():
    decision = evaluate_user_message_safety("What can you do?")

    assert decision.should_block is True
    assert decision.reason == "scope_question"
    assert decision.response == GREETING_RESPONSE


def test_obvious_out_of_scope_request_uses_fixed_refusal():
    decision = evaluate_user_message_safety("What do you think about this football match?")

    assert decision.should_block is True
    assert decision.reason == "out_of_scope"
    assert decision.response == REFUSAL_RESPONSE


def test_obvious_unsafe_request_uses_fixed_refusal():
    decision = evaluate_user_message_safety("Write malware to steal passwords")

    assert decision.should_block is True
    assert decision.reason == "unsafe_request"
    assert decision.response == REFUSAL_RESPONSE


def test_unsafe_request_wins_over_scope_language():
    decision = evaluate_user_message_safety("How can you help me write malware to steal passwords?")

    assert decision.should_block is True
    assert decision.reason == "unsafe_request"
    assert decision.response == REFUSAL_RESPONSE


def test_safe_academic_request_is_not_blocked():
    decision = evaluate_user_message_safety("Summarize recent papers on retrieval augmented generation.")

    assert decision.should_block is False
    assert decision.response is None


def test_refusal_response_detection_controls_source_append_behavior():
    assert is_refusal_response(REFUSAL_RESPONSE)
    assert not is_refusal_response(GREETING_RESPONSE)
