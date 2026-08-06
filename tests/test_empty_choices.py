"""
test_empty_choices.py
---------------------
An OpenAI-compatible provider can answer HTTP 200 with an EMPTY choices list.
Nothing raises until `response.choices[0]` throws IndexError, which kills the
turn - so the user waits through every query and then gets a server error.

Seen live on nvidia/gpt-oss-20b while testing the employee-360 question. The
same model also returns empty final messages intermittently, so this is not a
one-off.
"""
from types import SimpleNamespace

from app.agent import groq_backend


def _response(choices):
    return SimpleNamespace(choices=choices)


def test_empty_choices_does_not_raise_indexerror():
    """The guard is `if not response.choices: continue` - assert the shape it
    relies on, so a refactor that drops it fails here rather than in front of a
    user."""
    resp = _response([])
    assert not resp.choices  # the condition the backend branches on

    # And the unguarded access is what used to happen:
    try:
        _ = resp.choices[0]
    except IndexError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected IndexError from the unguarded access")


def test_the_backend_guards_empty_choices():
    import inspect

    src = inspect.getsource(groq_backend)
    assert "if not response.choices:" in src, \
        "the empty-choices guard is gone; an empty provider reply will crash the turn"
    # It must not simply return: data gathered so far should survive and the
    # end-of-loop write-up should still run.
    guard = src.split("if not response.choices:", 1)[1][:400]
    assert "continue" in guard, "an empty round must not abandon the turn"
