# Model configurations

Empty at M0 by design. No model is defined in this repository yet.

## Planned files

`telemetry_v0.yaml` (M1)
: Decoder-only transformer over telemetry tokens alone: layers, width, heads,
  context length in grid steps, and the vocabulary layout sizes it must agree with.
  Sized against one 8 GB GPU, so context length and width are budget decisions, not
  aspirations.

`joint_v0.yaml` (M3)
: The same decoder over the joint vocabulary, plus how a text segment and a
  telemetry window are packed into one sequence.

The risk head and the abstention mechanism are part of the model config, not an
afterthought: the endpoint is calibrated risk with abstention, so the head that
produces it is specified alongside the backbone.
