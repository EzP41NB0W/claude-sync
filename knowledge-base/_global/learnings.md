# Global Learnings

Cross-project notes that don't belong to any one project's handoff.md.
Rolled up automatically as the "_learnings" section.

## Standing conventions (read this first — any session, any product)

These apply across every project in this knowledge base, whichever Claude
product or session is reading. If chat-level preferences are absent, outdated
or conflicting, **this file is the durable source of truth**. Setup
(SETUP-FOR-CLAUDE.md) tailors these to the owner; edit freely after that.

1. **Verify before claiming "done" / "working."** Before marking anything
   confirmed in a handoff.md, read the actual current file, run the actual
   build, or see the actual hardware/output. A claim that is silently false
   is the most expensive failure this system can have: the next session
   builds on it. If you only reasoned about it, write "untested" / "on paper".
2. **Tag the source when several tools touch one project.** If a piece of
   code or a claim came from a different session, product or tool, say so in
   the handoff entry. Record what the owner *said* as "he/she/they said", not
   as fact: notes launder guesses into evidence.
3. **Match existing project folder names exactly** (case, hyphens, spacing)
   before creating or writing to one. Check `knowledge-base/projects/` first:
   a "new" task is often a continuation of an existing project.
4. **Code lives in a project repo (`code/<project-name>/` or another
   `repo_roots` folder in `claude-sync.json`); notes live in
   `knowledge-base/projects/<project-name>/handoff.md`, or in the repo's own
   `HANDOFF.md` when `notes_home` is `repo`.** Never scatter project folders
   elsewhere on disk. The two-layer rule below applies to central (`kb`)
   notes; in-repo notes are committed with the code.
   - **Two layers of git.** The knowledge-base root ignores `code/`; each
     `code/<name>/` is its OWN repo. A root commit after code work succeeds and
     contains none of the code. Commit inside the project repo for source, at
     the root for notes, and check `git show --stat HEAD` in both. The
     `commit-msg` hook catches the common case.
   - **`git init` is part of creating a project**, along with its
     `.gitignore` and `bash tools/githooks/install.sh` (hooks are per-repo
     config and do not come along by themselves).
   - **Pushing follows the push policy** in `tools/githooks/push-policy`
     (default: nothing leaves the machine). Local commits are always fine and
     are the backup. Anything that leaves the machine (push, creating a remote
     repo) needs the owner's explicit go-ahead unless the policy already
     allows it.
5. **Dead ends and cross-project lessons go HERE** (Lessons section below),
   not buried in one project's handoff, so every project's sessions see them.
   `python rollup.py learn "..."`, the dashboard box, or the `add_learning`
   MCP tool.
6. **Never write credentials, API keys or tokens into any of these files.**
   Secrets live in their own gitignored files, filled in locally, never typed
   into chat or saved in notes.
7. **Privacy and security first**, especially other people's information.
   Collect the minimum a task needs; ask for redaction before documents are
   shared; keep third-party documents out of git (gitignore the folder BEFORE
   the first file lands) and out of notes; publish only what the owner chose
   to publish. When privacy and convenience conflict, pick privacy and say why
   in one line.

## Starter lessons (general-purpose, from the system's original owner)

- **Mutation-test your checks.** Break the thing a check claims to catch (one
  textual change in a copy, run it, expect FAIL) before trusting its PASS. A
  CAD gate here passed with snap features pointing the wrong way, and a clash
  test passed with a connector opening smaller than the connector, until
  mutated.
- **`tool | grep PATTERN && next-step` gates on grep, not on the tool.** A
  failed build whose output contains the word you grep for still lets the
  chain continue (and a commit land claiming "compiles"). Gate on the tool's
  own exit code.
- **Verify the artifact, not the model.** Measure the exported file (STL,
  binary, built page) rather than the in-memory model that produced it; the
  export step has its own failure modes.
- **Windows Task Scheduler: after editing a task, read back NextRunTime.** A
  repetition hung off an at-logon trigger is not live until the next logon;
  a blank NextRunTime means it will never fire on its own.

## Lessons

<!-- add_learning / `rollup.py learn` appends below this line -->
