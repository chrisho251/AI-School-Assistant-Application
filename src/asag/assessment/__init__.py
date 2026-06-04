"""Question-type registry — maps a QuestionType to its generator (and grader).

New question types plug in via ``register_question_type`` without touching the
orchestrator (open/closed). POC registers ``mcq`` + ``short`` generators here;
the matching graders are registered by ``asag.assessment.graders`` (Day 7).

    register_question_type(QuestionType.essay, generator=gen_essay, grader=grade_essay)
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from asag.models.grading import GradeResult
from asag.models.question import Question, QuestionType

GeneratorFn = Callable[..., Awaitable[list[Question]]]
GraderFn = Callable[..., Awaitable[GradeResult]]


@dataclass
class QuestionTypeSpec:
    """The pluggable behaviour for one question type."""

    generator: GeneratorFn | None = None
    grader: GraderFn | None = None


_REGISTRY: dict[QuestionType, QuestionTypeSpec] = {}


def register_question_type(
    qtype: QuestionType,
    *,
    generator: GeneratorFn | None = None,
    grader: GraderFn | None = None,
) -> None:
    """Register (or extend) the generator/grader pair for *qtype*.

    Calling twice merges: passing only a grader later keeps the existing generator.
    """
    spec = _REGISTRY.setdefault(qtype, QuestionTypeSpec())
    if generator is not None:
        spec.generator = generator
    if grader is not None:
        spec.grader = grader


def get_generator(qtype: QuestionType) -> GeneratorFn:
    """Return the generator for *qtype*.

    Raises:
        KeyError: if no generator is registered for *qtype*.
    """
    spec = _REGISTRY.get(qtype)
    if spec is None or spec.generator is None:
        raise KeyError(f"No generator registered for question type {qtype!r}")
    return spec.generator


def get_grader(qtype: QuestionType) -> GraderFn:
    """Return the grader for *qtype*.

    Raises:
        KeyError: if no grader is registered for *qtype*.
    """
    spec = _REGISTRY.get(qtype)
    if spec is None or spec.grader is None:
        raise KeyError(f"No grader registered for question type {qtype!r}")
    return spec.grader


def registered_types() -> list[QuestionType]:
    """Return question types that have a generator registered."""
    return [qt for qt, spec in _REGISTRY.items() if spec.generator is not None]


# ---- Register built-in generators (POC: mcq + short) ----
from asag.assessment.generators.mcq import generate_mcq  # noqa: E402
from asag.assessment.generators.short import generate_short  # noqa: E402

register_question_type(QuestionType.mcq, generator=generate_mcq)
register_question_type(QuestionType.short, generator=generate_short)
