# Mobile Native Orchestration Quickstart

Use this file when you want to start a long-running implementation session for the native mobile companion.

Primary prompt:
- [docs/mobile-native-orchestration-prompt.md](/path/to/outlays-desktop/docs/mobile-native-orchestration-prompt.md:1)

Paste the full prompt into the implementation agent and let it execute against this repo:
- repo root: `/path/to/outlays-desktop`

The prompt is already grounded in:
- the repo rules
- the mobile vision
- the native implementation plan
- the mobile agent runbook
- the local toolchain on this machine

Recommended usage:
- start a fresh agent session
- paste the full orchestration prompt
- allow it to read the referenced docs and work through the milestones
- if sub-agents are available in that environment, allow them for bounded Android/iOS parallelization
