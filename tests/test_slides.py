import io

import pytest
from pptx import Presentation

from botstack.slides import deck_to_pptx


@pytest.mark.parametrize(
    "slides",
    [
        [],
        [
            {
                "heading": "Our solar system",
                "bullets": ["Eight planets orbit the Sun."],
                "speaker_notes": "Ask the class to name the planets.",
            }
        ],
        [
            {
                "heading": "Start with a question",
                "bullets": ["What keeps planets in orbit?", "Where does gravity act?"],
                "speaker_notes": "Pause for answers.\nExplain the role of gravity.",
            },
            {
                "heading": "Try an experiment",
                "bullets": ["Compare two falling objects."],
                "speaker_notes": "Use a ball and a sheet of paper. Discuss the results.",
            },
        ],
    ],
    ids=["cover-only", "one-content-slide", "multiple-content-slides"],
)
def test_deck_to_pptx_returns_readable_bytes_with_speaker_notes(slides):
    deck = {
        "title": "A science lesson",
        "subtitle": "Explore and explain",
        "slides": slides,
    }

    result = deck_to_pptx(deck)

    assert isinstance(result, bytes)
    presentation = Presentation(io.BytesIO(result))
    assert len(presentation.slides) == 1 + len(slides)
    for index, slide in enumerate(slides, start=1):
        assert (
            presentation.slides[index].notes_slide.notes_text_frame.text
            == slide["speaker_notes"]
        )
