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

## Live run

- [ ] Complete and verify a real Valkyrie run with private evaluation.
      Codex run `3783d623-4e29-468c-996c-916bb900e162` was accepted and is in
      progress. There is no final score yet.
- [ ] Save run result, error record, trace and outputs under the private
      run directory. Publish only non-sensitive execution metadata.

## Submission

- [ ] Push and verify the clean GitHub repository.
- [ ] Author writes the personal paragraph at the top of the README.
- [ ] Author selects submission visibility and submits the link in the
      hackathon portal. The initial GitHub repository is private.
- [ ] Use a durable authenticated deployment if organizer replay will outlive
      the local service and tunnel.
