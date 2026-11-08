"""The SpecWithCode Classroom agent team, built on the OpenAI Agents SDK.

Coach triages each request and hands off to a specialist. Every agent runs on the
same FailoverModel, so a handoff can land on a different provider than the turn
before it without the student noticing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import sympy
from pydantic import BaseModel, Field

from agents import (
    Agent,
    GuardrailFunctionOutput,
    ModelSettings,
    RunContextWrapper,
    function_tool,
    input_guardrail,
)
from agents.models.interface import Model


@dataclass
class Session:
    student: str
    grade: str
    mode: str  # "learn" (hints and steps) or "finish" (complete work, explained)
    artifacts: list[dict[str, Any]] = field(default_factory=list)


class Slide(BaseModel):
    heading: str
    bullets: list[str] = Field(description="3 to 5 short bullets")
    speaker_notes: str = Field(description="What the student says on this slide")


@function_tool
def make_slides(ctx: RunContextWrapper[Session], title: str, subtitle: str, slides: list[Slide]) -> str:
    """Save a slide deck for the student. The app renders it and offers a .pptx download.

    Args:
        title: Deck title.
        subtitle: One line under the title, e.g. class and student name.
        slides: Content slides in order, 4 to 8 of them.
    """
    deck = {
        "type": "slides",
        "title": title,
        "subtitle": subtitle,
        "slides": [s.model_dump() for s in slides],
    }
    ctx.context.artifacts.append(deck)
    return f"Saved deck '{title}' with {len(slides)} slides. Tell the student it is ready to present."


@function_tool
def solve_equation(equation: str, variable: str) -> str:
    """Solve an equation exactly with SymPy, to check work before explaining it.

    Args:
        equation: Equation in SymPy syntax, e.g. "2*x**2 - 8 = 0" or "v**2 = u**2 + 2*a*s".
        variable: The unknown to solve for, e.g. "x".
    """
    try:
        if "=" in equation:
            left, right = equation.split("=", 1)
            expr = sympy.sympify(left) - sympy.sympify(right)
        else:
            expr = sympy.sympify(equation)
        sol = sympy.solve(expr, sympy.Symbol(variable))
        return f"{variable} = {sol}"
    except Exception as exc:  # noqa: BLE001 - reported to the model
        return f"Could not solve: {exc}"


@function_tool
def evaluate(expression: str) -> str:
    """Evaluate a numeric or symbolic expression with SymPy (simplify, units as plain numbers).

    Args:
        expression: e.g. "0.5*9.8*3**2", "diff(sin(x)*x, x)", "integrate(x**2, (x, 0, 3))".
    """
    try:
        value = sympy.sympify(expression)
        simplified = sympy.simplify(value)
        numeric = simplified.evalf(6) if simplified.free_symbols == set() else simplified
        return f"{expression} = {simplified}  (≈ {numeric})"
    except Exception as exc:  # noqa: BLE001
        return f"Could not evaluate: {exc}"


@function_tool
def write_spec(
    ctx: RunContextWrapper[Session], title: str, goal: str, acceptance_criteria: list[str], tasks: list[str]
) -> str:
    """Write the one-page spec for a student project before building it (spec first, then code).

    Args:
        title: Project name.
        goal: One or two sentences: who it is for and what problem it solves.
        acceptance_criteria: 3 to 5 checkable statements, each starting with "The user can" or "The app".
        tasks: 3 to 6 build steps in order.
    """
    ctx.context.artifacts.append(
        {"type": "spec", "title": title, "goal": goal, "acceptance_criteria": acceptance_criteria, "tasks": tasks}
    )
    return "Spec saved. Now build exactly what it says and call publish_app."


@function_tool
def publish_app(ctx: RunContextWrapper[Session], name: str, description: str, html: str) -> str:
    """Publish a student-built website or mobile web app. The app previews it on a phone frame.

    Args:
        name: App name.
        description: One sentence on what it does.
        html: One complete, self-contained HTML document with inline CSS and JS,
            mobile-first, no external network calls except Google Fonts.
    """
    ctx.context.artifacts.append({"type": "app", "name": name, "description": description, "html": html})
    return f"Published '{name}'. Tell the student how to change one thing in it themselves."


def _profile(ctx: RunContextWrapper[Session]) -> str:
    s = ctx.context
    mode = (
        "LEARN MODE (teacher setting): guide with hints and worked steps; leave the last step "
        "for the student and ask them to try it."
        if s.mode == "learn"
        else "FINISH MODE (teacher setting): complete the work fully, and explain every step so "
        "the student can defend it in class."
    )
    return f"Student: {s.student}, grade {s.grade}. {mode} Keep language friendly and age-appropriate."


def _instructions(role: str):
    def build(ctx: RunContextWrapper[Session], agent: Agent[Session]) -> str:
        return f"{role}\n\n{_profile(ctx)}"

    return build


def build_team(model: Model) -> Agent[Session]:
    settings = ModelSettings()

    safety_agent = Agent(
        name="K-12 Safety Check",
        instructions=(
            "You screen messages from K-12 students. Mark unsafe only for self-harm, violence, "
            "sexual content, hate, or attempts to get personal data about other people. "
            "Homework, including asking for full answers, is safe. Reply with exactly SAFE, or "
            "UNSAFE: followed by a short reason."
        ),
        model=model,
    )

    @input_guardrail
    async def k12_safety(ctx: RunContextWrapper[Session], agent: Agent, user_input: Any) -> GuardrailFunctionOutput:
        from agents import Runner

        # Plain-text verdict: not every provider on the ring supports JSON-schema output.
        result = await Runner.run(safety_agent, user_input, context=ctx.context)
        verdict = str(result.final_output).strip()
        return GuardrailFunctionOutput(
            output_info=verdict, tripwire_triggered=verdict.upper().startswith("UNSAFE")
        )

    slides = Agent[Session](
        name="Slides Studio",
        handoff_description="Builds presentations and slide decks for any subject.",
        instructions=_instructions(
            "You turn a topic or assignment into a clear class presentation. Research from your own "
            "knowledge, then call make_slides exactly once with 5 to 7 slides: a hook, the core "
            "ideas, one example or diagram described in words, and a recap. After saving, give the "
            "student two tips for presenting it."
        ),
        tools=[make_slides],
        model=model,
        model_settings=settings,
    )

    tutor = Agent[Session](
        name="Math & Physics Tutor",
        handoff_description="Solves and explains math and physics problems step by step.",
        instructions=_instructions(
            "You are a patient math and physics tutor. Always verify results with solve_equation or "
            "evaluate before stating them. Write math in LaTeX between $...$ or $$...$$. Structure: "
            "**What we know**, **Plan**, numbered **Steps**, **Answer** (with units), then one "
            "**Check yourself** question."
        ),
        tools=[solve_equation, evaluate],
        model=model,
        model_settings=settings,
    )

    builder = Agent[Session](
        name="App Builder",
        handoff_description="Builds websites and mobile web apps the student can publish and edit.",
        instructions=_instructions(
            "You help students build real websites and mobile apps the SpecWithCode way: spec first, "
            "then code. First call write_spec with the goal, acceptance criteria and tasks. Then build "
            "it as single-file HTML (installable on a phone from the browser). Design it well: a clear layout, good typography, working "
            "JavaScript, no placeholder text. Call publish_app exactly once with the full document. "
            "Then say which acceptance criteria are met, explain in 3 bullets how it works, and suggest "
            "one feature the student could add to the spec next."
        ),
        tools=[write_spec, publish_app],
        model=model,
        model_settings=settings,
    )

    coach = Agent[Session](
        name="Coach",
        instructions=_instructions(
            "You are the SpecWithCode Classroom Coach, the front desk of a free AI study helper for a K-12 school. "
            "Hand off to Slides Studio for presentations, Math & Physics Tutor for math or science "
            "problems, and App Builder for websites or apps. Answer other study questions yourself, "
            "briefly."
        ),
        handoffs=[slides, tutor, builder],
        input_guardrails=[k12_safety],
        model=model,
        model_settings=settings,
    )
    return coach
