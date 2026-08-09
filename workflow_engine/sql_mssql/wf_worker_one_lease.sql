/*
  RETIRED.

  A global one-live-lease-per-worker gate was briefly used for GPU Align safety.
  That policy belongs on the action catalog (``dispatch.max_per_worker`` /
  ``dispatch.exclusive_worker``), not as a hard-wired engine rule.

  Apply instead:
    - wf_action_dispatch_concurrency.sql  (columns + 9-arg upsert)
    - wf_worker_desired_state.sql         (claim SP reads catalog columns)
*/
