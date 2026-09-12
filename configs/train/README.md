# Training configurations

The code these drive lives in `src/faultline/training/` and `src/faultline/evaluation/`.

## Files

`telemetry_v0.yaml` (M1e)
: What the runs do to the models in `configs/model/ladder_v0.yaml`: the optimiser, the
  schedule, the batch and accumulation, the precision, the gradient clip, the budgets, the
  two strides, and which of the four runs the ladder makes. It names the tokenizer
  configuration whose shards it reads, so a checkpoint traces back to the exact corpus
  that produced it.

  **Four runs at every rung**: the language model, a frozen probe on its backbone, a
  fine-tune, and the same head and budget on a *randomly initialised* backbone. The fourth
  is what makes the ladder an experiment rather than a size sweep, and the configuration
  refuses to load if its budget differs from the fine-tuned run's in any respect: the
  comparison is initialisation and nothing else, enforced rather than trusted.

  **Multi-seed runs are not optional**, so the seeds are in the model config beside the
  rungs they belong to rather than passed on a command line. Three at the small rungs and
  one at the large ones is what one 8 GB card allowed; the report says so and quotes the
  measured spread as the error bar rather than implying three throughout.

  **The training stride is not 1** and the file says why: successive windows share 143 of
  their 144 steps, so at stride 1 the effective sample size is far below the token count.
  Evaluation keeps stride 1, because a risk model is scored on every step it would have to
  make a call on.

`text_v0.yaml` (M2), `joint_v0.yaml` (M3)
: The same for the text-only and joint decoders.
