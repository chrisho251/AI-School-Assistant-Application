"""Unit tests for the question-type registry."""

from __future__ import annotations

import pytest

from asag.assessment import get_generator, get_grader, registered_types
from asag.assessment.generators.mcq import generate_mcq
from asag.assessment.generators.short import generate_short
from asag.models.question import QuestionType


def test_poc_registers_mcq_and_short() -> None:
    types = registered_types()
    assert QuestionType.mcq in types
    assert QuestionType.short in types


def test_get_generator_returns_registered_fn() -> None:
    assert get_generator(QuestionType.mcq) is generate_mcq
    assert get_generator(QuestionType.short) is generate_short


def test_get_generator_unregistered_raises() -> None:
    # essay is an extension hook with no generator in the POC
    with pytest.raises(KeyError):
        get_generator(QuestionType.essay)


def test_get_grader_not_registered_yet() -> None:
    # graders are wired in Day 7
    with pytest.raises(KeyError):
        get_grader(QuestionType.mcq)
