import pytest

from run_local_direct_beliefs import strict_probabilities


def test_valid_distribution_preserved():
    assert strict_probabilities('{"probabilities":[0,0.1,0.2,0.3,0.4,0]}') == [0,.1,.2,.3,.4,0]


@pytest.mark.parametrize("text", [
    '{"probabilities":[0,0,0,0,0,0]}',
    '{"probabilities":[true,0,0,0,0,0]}',
    '{"probabilities":[NaN,0,0,0,0,1]}',
    '{"probabilities":[1,0,0,0,0]}',
    '{"probabilities":[1,0,0,0,0,0],"extra":1}',
    '```json\n{"probabilities":[1,0,0,0,0,0]}\n```',
])
def test_invalid_outputs_are_not_repaired_or_normalized(text):
    with pytest.raises(ValueError):
        strict_probabilities(text)
