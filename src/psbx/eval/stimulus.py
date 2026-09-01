"""Track A: headline/media stimulus items reused from e2012 questions."""

from __future__ import annotations

from psbx.schemas import MediaStimulusItem, Question


def items_from_questions(
    questions: list[Question],
    *,
    epoch_id: str = "e2012",
) -> list[MediaStimulusItem]:
    """Each binary e2012 question is a media-stimulus → later-outcome item.

    The stimulus is the FrozenEpochEnv contemporaneous pack (headlines/outlets
    with published_at ≤ cutoff). The score field is ground_truth. Poll-share
    targets are not invented here; add them only when a dated series exists.
    """
    items: list[MediaStimulusItem] = []
    for question in questions:
        items.append(
            MediaStimulusItem(
                id=f"media-{question.id}",
                question_id=question.id,
                epoch_id=question.epoch_id or epoch_id,
                stimulus_kind="contemporaneous_media",
                response_kind="binary_outcome",
                score_field="ground_truth",
                note=(
                    "Stimulus = contemporaneous media pack. "
                    "Score predicted public/political response against later "
                    f"{question.category} outcome. Surveys/ads/studies condition "
                    "the demographic swarm; they are not the headline prompt."
                ),
            )
        )
    return items
