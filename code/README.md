# code/

Each project's source lives in its own folder here, and **each folder is its
own git repo** (`git init` when you create it, then
`bash tools/githooks/install.sh` from the claude-sync root so the hooks cover
it). The knowledge-base root repo ignores everything in `code/` except this
README.

Whether these repos may be pushed (e.g. to GitHub) is decided by
`tools/githooks/push-policy`: set it to `code` to let every project here push
while your notes stay local.
