# BotStack

Python 3.12, FastAPI, OpenAI Agents SDK (`openai-agents`). Frontend is plain HTML/CSS/JS in `static/`.

- `botstack/router.py`: Key Ring providers and `FailoverModel` (Agents SDK `Model`).
- `botstack/team.py`: Coach agent, handoffs to Slides Studio, Math & Physics Tutor, App Builder; K-12 input guardrail.
- `botstack/app.py`: HTTP API. `api/index.py` is the Vercel entry.
- Tests: `pytest -q` in `tests/`, offline only. Never call a real provider from tests.
- Never commit `.env` or keys.
