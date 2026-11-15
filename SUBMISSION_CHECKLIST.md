# EvalScout submission checklist

## Completed

- [x] Frozen one retail investigation task and its two disjoint sets of ten.
- [x] Preserved source provenance, license, human annotations, and prior results.
- [x] Wired the official Valkyrie starter to list tasks, provision the agent, upload
      allowlisted inputs, run a private grader, and aggregate the score.
- [x] Verified the authenticated service responds through its tunnel and Valkyrie
      lists the single task.
- [x] Tested grading, duplicate and blanket-flag handling, upload isolation,
      invalid output handling, and offline Linux execution.
- [x] Verified the local Streamlit dashboard responds.
- [x] Prepared the README author placeholder, provenance, scoring rubric,
      local model comparisons, examples, and figures.

## Valkyrie runs

- [x] Completed the Modal-hosted custom-service run
      `f21db0b6-dd9e-46a9-91a5-37a0fa331329`. It returned **0** with
      `invalid_findings` because three evidence lists exceeded a validator
      cap absent from the task instructions. This score is a protocol failure.
- [x] Saved its result, errors, rollout, and available harness artifacts
      in the organizer's private run directory.
- [x] Relaxed the validator to accept any unique, in-range positions and
      verified the Harbor verifier locally in a network-disabled Linux container.
- [x] Published the official-format Harbor dataset, `evalscout-harbor/retail@v2`.
- [x] Completed the native Harbor v2 Codex run
      `69eb9c6b-88c9-4e42-b250-1a197a15a794` on Modal: **38.1/100**.
      Archived the result, task status, logs, and outputs privately.
- [ ] Record Claude Code on Harbor v1
      `ab8590b6-59e6-4d01-830f-5413aaf9b21a` when complete. V1 and v2 use
      different validation rules; their scores are not directly comparable.

## Submission

- [x] Confirmed the team-hosted dataset `evalscout-harbor/retail@v2` and
      the completed Sol run, `69eb9c6b-88c9-4e42-b250-1a197a15a794`.
- [x] Included local frontier-model figures and separately identified the
      hosted result in the README. The run ID can be used as the optional
      Valkyrie artifact in the submission.
- [ ] Save the project in the [hackathon portal](https://hackathon.vals.ai/)
      using the [GitHub repository](https://github.com/Vbdata13/evalscout).
      Include the dataset handle and completed run ID where the form permits.

- [x] Pushed and verified the clean private GitHub repository.
- [ ] Author writes the personal paragraph at the top of the README.
- [ ] Give judges access to the repository. It is currently private.
- [ ] A public Valkyrie browser permalink for this run has not been verified.
      The event instructions allow including the run ID.
- [x] Durable Modal deployment available. The Harbor route also supports
      replay through the hosted dataset without the custom service.
