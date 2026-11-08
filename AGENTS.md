# SpecWithCode Classroom

Python 3.12, FastAPI, OpenAI Agents SDK (`openai-agents`). Frontend is plain HTML/CSS/JS in `static/`.

- `swc_classroom/router.py`: Key Ring providers and `FailoverModel` (Agents SDK `Model`).
- `swc_classroom/team.py`: Coach agent, handoffs to Slides Studio, Math & Physics Tutor, App Builder; K-12 input guardrail.
- `swc_classroom/app.py`: HTTP API. `api/index.py` is the Vercel entry.
- Tests: `pytest -q` in `tests/`, offline only. Never call a real provider from tests.
- Never commit `.env` or keys.
