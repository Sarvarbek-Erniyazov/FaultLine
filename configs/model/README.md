# Model configurations

The code these drive lives in `src/faultline/model/`.

## Files

`ladder_v0.yaml` (M1e)
: The size ladder: four rungs, and the context they all share. The architecture and only
  the architecture -- what a run *does* to these models is `configs/train/`. The two are
  separate because they change on different occasions, and the ladder report records the
  hash of both.

  **Context is held fixed across the ladder.** Varying it with size would confound the two
  and neither axis could then be read; context length is a separate ablation.
  **Parameters are counted excluding embeddings**, which is the axis of every plot in the
  report: the embeddings scale with the vocabulary and the context, and at the widest rung
  they would dominate the two narrowest.

  The head count is not part of the size axis -- attention costs 4 d^2 whatever it is --
  but it decides whether the attention runs on the fused kernel at all, which needs a head
  dimension divisible by 8. The file says which rung that constrained and what the
  fallback cost, and `tests/model/test_transformer.py` fails if a rung ever misses it.

`joint_v0.yaml` (M3)
: The same decoder over the joint vocabulary, plus how a text segment and a telemetry
  window are packed into one sequence.

The risk head is part of this file, not an afterthought: the endpoint is calibrated risk
with abstention, so the head that produces it is specified alongside the backbone.
