"""Grader registry — registers each question type's grader into the shared registry.

Mirrors ``assessment/generators`` registration: importing this module wires the
built-in graders into the question-type registry so ``get_grader(qtype)`` resolves.
New types add a grader here without touching the orchestrator (open/closed).

    register_question_type(QuestionType.essay, grader=grade_essay)
"""

from __future__ import annotations

from asag.assessment import register_question_type
from asag.assessment.graders.mcq import grade_mcq
from asag.assessment.graders.short import grade_short
from asag.models.question import QuestionType

register_question_type(QuestionType.mcq, grader=grade_mcq)
register_question_type(QuestionType.short, grader=grade_short)
