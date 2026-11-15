# EvalScout benchmark methodology

## Task and provenance

There is one long-horizon task, `evalscout-retail`. It uses the ten
development trajectories from the frozen human annotation experiment.
The disjoint private test split has ten trajectories. Both splits use ten
distinct Sierra task IDs, five source successes and five failures per
split. Outcome balance was used for curation only. We preferentially
sampled diverse observed tool profiles, so the split is not a prevalence
estimate. Source is [Sierra τ-bench](https://github.com/sierra-research/tau-bench)
commit `59a200c6d575d595120f1cb70fea53cef0632f6b`, the
`historical_trajectories/gpt-4o-retail.json` file, and the retail policy
at that same commit. Upstream MIT terms are in [SIERRA_LICENSE](SIERRA_LICENSE).
Trace IDs are EvalScout aliases. Public row mapping and content digests are
in [provenance.json](provenance.json). The private mapping stays local.

## Rubric

| Component | Points | Operational check |
|---|---:|---|
| Discovery | 25 | Distinct verified development incidents with a matching trace, specific event, and failure language |
| Breadth | 15 | Distinct supported failure mechanisms, once per mechanism |
| Severity | 10 | Severity agrees with the adjudicated severity on matched incidents |
| Execution | 10 | Submitted Python runs and produces a valid prediction for every declared category on all 10 traces |
| Unseen detection | 30 | Distinct verified held-out incidents with matching evidence positions and category semantics |
| Recommendations | 5 | Nonempty recommendations artifact, checked for presence only |
| Selectivity | 5 | The evaluator makes at least one positive decision without any category flagging every trace |
| Verified contradictions | up to −15 | Only checked claims and matched test negatives that were explicitly adjudicated |

A missed verified critical incident caps the numerical score at 79 and
prevents a resolved task. Resolution also requires valid execution and
at least 70 points. A category that marks every test case present receives
no unseen-match credit. Duplicates cannot multiply incident or breadth
credit. Unmatched evidence is unscored unless it contradicts a verified
negative anchor. It may still represent a genuine additional issue.
No ticket-wide success reward is used as a failure-specific label. Overall
precision and unverified negatives are unmeasured.

Scoring uses private, deterministic regex and event matching rather than a
paid judge. It is reproducible and may undercount valid novel terminology
or overmatch ambiguous language near an anchored event. The reference comes
from human comments and separate model-assisted transcript adjudication.
The small, deliberately balanced sample cannot establish production
prevalence. The benchmark supports submitted offline Python evaluators.
A proposed LLM judge can be described as a recommendation, and hosted judge
calls are unavailable inside the evaluator.

## Security boundaries

The service uploads exactly four public files to the agent sandbox and
creates an empty submission directory. The run allows only model inference
API destinations. Setup and evaluation have empty service egress lists.
The official harness provisions its dependencies before the agent phase.
The grader downloads three bounded files and runs the submitted evaluator in
a fresh non-root Linux container with networking disabled, read-only
filesystem, dropped capabilities, and resource limits. The container
receives hidden transcripts via stdin. Labels, reference data, source checkout,
service credentials and rubric implementation are never mounted into that
container. The service returns aggregate scores without raw evaluator output.
Use a secret header for tunnel deployments.
