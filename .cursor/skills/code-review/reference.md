# P0–P4 Style Guide

Canonical rules from [sglang-diffusion-routing#32](https://github.com/zhaochenyang20/sglang-diffusion-routing/issues/32). Priority: Correctness (P0) > Performance (P1) > Maintainability (P2) > Style (P3) > Process (P4).

## P0 — Correctness

**Fail Fast:**

- Use `assert` for programmer error invariants. Use `raise ValueError/TypeError` for bad user input.
- Validate inputs at public API entry points and system boundaries (HTTP handlers, config parsing). Internal helpers can assume valid inputs.
- Use early returns and guard clauses at the top of functions instead of deeply nested if-else blocks.
- Do NOT overprotect: if an operation is correct 99% of the time, do not add defensive handling for its failure. LLMs tend to over-protect — resist this instinct.
- Do NOT over-catch: `try/except` must have a clear, narrow protection region. Never wrap a large code block in a single `try/except`.

**Concurrency & Thread Safety:**

- Document thread-safety guarantees explicitly for classes/functions accessed from multiple threads.
- Minimize lock scope. Never perform I/O or GPU operations while holding a lock.
- Prefer message passing (queues) over shared mutable state.

**Resource Management:**

- Free large intermediate tensors with `del` + `torch.cuda.empty_cache()` ONLY when profiling proves it necessary. Do not scatter these defensively.
- File handles, sockets, CUDA streams must use context managers (`with` statements).
- Any cache or buffer must have a bounded size or eviction policy. No `append`-only lists in long-running loops.

## P1 — Performance

This is a high-performance system where every millisecond matters.

- Strictly avoid frequent `.item()`, `.cpu()`, or `.tolist()` calls in the model inference path.
- Keep data processing vectorized on the GPU whenever possible. CPU fallbacks in hot paths are unacceptable.
- Optimize hot paths with low-overhead implementations. Flag any unnecessary Python-level overhead in tight loops.

## P2 — Maintainability

**Architecture & Decoupling:**

- DRY: Duplicate code exceeding 5 lines must be extracted into shared functions.
- Files exceeding 2,000 lines must be split (Mixin patterns or sub-modules).
- Functions should rarely exceed 50 lines (excluding docstrings). Extract logical sub-steps into private helpers.

**Naming Clarity:**

- No abbreviations in public APIs: `request_count` not `req_cnt`. Exceptions: widely-known terms (`num`, `idx`, `cfg`, `bs`).
- Boolean names: prefix with `is_`, `has_`, `should_`, `can_`.
- Symmetry: consistent pairs — `start/stop`, `begin/end`, `open/close`, `send/recv`. Do not mix (e.g., no `start/finish`).
- No generic names: avoid `data`, `result`, `info`, `tmp`, `manager`, `handler` without qualification. Use `token_ids`, `decode_result`, etc.

**Imports:**

- Order: stdlib -> third-party -> local, separated by blank lines (`isort` style).
- Never use `from module import *`.
- Lazy imports for heavy optional dependencies inside the function that uses them.
- No circular imports — extract shared interfaces into a third module if needed.

**Constants:**

- No magic numbers. Extract into named constants: `MAX_BATCH_SIZE = 256`.
- Exception: `0`, `1`, `-1` in obvious arithmetic/indexing.

## P3 — Style

**Function Purity:**

- Prioritize pure functions. Avoid in-place modification of input arguments.
- Exception: in-place ops for extreme memory optimization in forward pass must have an explicit comment.

**Pythonic & Clean:**

- Lean constructors: keep `__init__` parameters concise. Pass only necessary parameters, not massive config objects.
- Avoid dynamic attributes (`getattr`/`setattr`). Code should be explicit.
- Ternary operator only for very simple cases. Complex logic uses standard `if-else`.
- Extract complex multi-line branch logic into standalone private functions.
- Complete branching: if an `if` assigns a variable or returns a value, always include `else`. Guard clauses (early return/raise/continue) don't need `else`. If branching exceeds 3 levels, refactor into `if/elif/.../else` or a dispatch dict.
- All public APIs and function signatures must include type hints.
- Use `_private` prefix for class/file-internal functions; otherwise it's public.
- Remove arbitrary debug comments and logs. Remove Chinese comments.

## P4 — Process

**Testing:**

- Provide verification scripts in PR descriptions that reviewers can copy & paste.
- Add CI unit tests for important features.
- Test the contract (inputs -> outputs), not internal state.
- Pin random seeds in tests for determinism.
- One assertion per concept per test function.
