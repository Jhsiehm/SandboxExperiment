"""Loss alignment checks with tiny analytic tensors, no model download."""
import math

import mlx.core as mx
import pytest

from score_local_message_loss import masked_nll


def test_uniform_loss_counts_only_completion_tokens():
    loss = masked_nll(mx.zeros((1, 4, 7)), [1, 2, 3, 4, 5], 3)
    assert float(loss.item()) == pytest.approx(2 * math.log(7), rel=1e-6)


def test_prompt_logits_are_excluded_and_completion_shift_is_correct():
    logits = mx.array([[[100., -100.], [-100., 100.], [100., -100.]]])
    # Prompt tokens positions0/1; completion positions2/3 predict1 then0.
    assert float(masked_nll(logits, [0, 0, 1, 0], 2).item()) == pytest.approx(0, abs=1e-5)
    assert float(masked_nll(logits, [0, 0, 0, 1], 2).item()) > 300


def test_empty_completion_rejected():
    with pytest.raises(ValueError):
        masked_nll(mx.zeros((1, 2, 7)), [1, 2, 3], 3)
