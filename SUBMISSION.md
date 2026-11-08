# BotStack: free AI study help that never runs out

**Event:** DevDay Exchange Community Hackathon: Miami, November 7 and 8, 2026

**Nonprofit:** South Florida K-12 schools, and the education nonprofits that fund their technology

**Repo:** https://github.com/anton-abyzov/botstack

**Live demo:** https://baseball-checks-due-biology.trycloudflare.com

## One line

BotStack pools a school's donated, free and low-cost AI subscriptions and machines, switches automatically when one runs out mid-class, and finishes real schoolwork: slides, math and physics, and student-built websites and apps.

## The problem

Students use free AI tiers every day, and the free tier runs out by mid-morning. Kids whose families pay keep working; everyone else stops. Schools often already hold more AI capacity than they use (nonprofit API credits, a cheap subscription, a free tier on the district account, a computer that can run an open model), but it is scattered across logins and nobody switches between them during a lesson.

## What we built

A working web app a school can deploy today.

- **Key Ring with automatic failover.** A custom OpenAI Agents SDK `Model` walks the school's providers in policy order (OpenAI nonprofit grant, DeepSeek, Gemini free tier, a library lab machine) and moves to the next one on a 429, quota error, outage, or when the school's daily token budget for that provider is spent. The switch happens per model call, so a task can start on one subscription and finish on another without the student seeing an error. Each answer shows its route, and the sidebar shows live budgets.
- **Agents that finish real schoolwork.** A Coach agent hands off to Slides Studio (decks with speaker notes, downloadable `.pptx`), a Math & Physics Tutor (step-by-step LaTeX, every result verified with SymPy), and an App Builder (complete mobile web apps, previewed in a phone frame).
- **Teacher controls and safety.** Learn mode gives hints and leaves the last step to the student; Finish mode completes the work and explains it. A K-12 input guardrail screens every request.

## How we used OpenAI

This project uses OpenAI to meet the hackathon requirements:

1. **OpenAI Agents SDK:** agents, handoffs, function tools, input guardrails, dynamic instructions, run context and tracing. Failover is implemented as an Agents SDK `Model`.
2. **OpenAI API:** the first provider on the Key Ring is the OpenAI API (`gpt-5.4-mini`) on the school's nonprofit credits, and Agents SDK traces export to the school's OpenAI dashboard whichever provider served the turn.
3. **Codex:** Codex wrote the offline test suite for the failover router and the slide exporter (`tests/`, 10 tests).

## Impact

- No student loses AI help at third period because a free tier ran out. Cost to families: $0.
- Schools get value from credits they already have, and can cap spend per provider per day.
- Output is real work, not chat: decks students present, math they can defend, apps they can open on their phones and keep editing.

## Demo (2 minutes)

See `DEMO.md`. Short version: tap **Run out** on the OpenAI grant, ask a physics question, and the answer arrives from DeepSeek with the route trail showing the switch; then generate a slide deck and a book club app.

## What's next

Persistent per-class budgets set by teachers, Google Classroom sign-in, and an offline mode that runs entirely on a school machine.

## Team

Anton Abyzov
