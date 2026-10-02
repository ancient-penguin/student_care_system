from app.passages_service import item_sentences, split_sentences


def test_split_basic_and_marker_start():
    text = "He is [[1]] tall. [[2]] children time. Mr. Kim came at 3 p.m. Today it rains!"
    s = split_sentences(text, {1: "very", 2: "Allow"})
    assert s == ["He is [[1]] tall.", "[[2]] children time.", "Mr. Kim came at 3 p.m. Today it rains!"]


def test_lowercase_after_period_does_not_split():
    assert split_sentences("See fig. two and e.g. this. Next one.", {}) == ["See fig. two and e.g. this.", "Next one."]


def test_quotes():
    assert split_sentences('He said "Stop." Then he left.', {}) == ['He said "Stop."', "Then he left."]


def test_context_overrides():
    items = [
        {"no": 1, "choice": "a", "context": None},
        {"no": 2, "choice": "b", "context": "Only [[2]] here."},
    ]
    out = item_sentences("One [[1]] and [[2]] together. Two.", items)
    assert out == {1: "One [[1]] and [[2]] together.", 2: "Only [[2]] here."}
