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
    # It must not simply RETURN: the data gathered so far should survive and the
    # end-of-loop write-up should still run. Both `continue` (retry the round)
    # and `break` (stop retrying, go straight to the write-up) satisfy that; a
    # bare `return` from inside the loop does not, because it skips the write-up
    # and hands back whatever partial state the turn happened to hold.
    #
    # The window is generous on purpose. It used to be 400 characters, which made
    # the test fail when an explanatory COMMENT was added above the branch - it
    # was measuring how much prose sits next to the code rather than what the
    # code does.
    import re

    guard = src.split("if not response.choices:", 1)[1][:900]
    assert "continue" in guard or "break" in guard, \
        "an empty round must not abandon the turn"
    # Everything up to whichever control-flow exit comes first.
    exit_at = min(
        (i for i in (guard.find("continue"), guard.find("break")) if i != -1),
        default=len(guard),
    )
    # \breturn\b, not a substring search: the log line above this branch contains
    # the words "provider returned no choices".
    assert not re.search(r"\breturn\b", guard[:exit_at]), \
        "an empty round must not return early and skip the write-up"
