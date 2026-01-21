Create a new commit for all of our uncommitted changes run git status && git diff HEAD && git status --porcelain to see what files are uncommitted add the untracked and changed files

Add an atomic commit message with an appropriate message

Add a tag such as "feat", "fix", "docs", etc. that reflects our work

Do all of this automatically and only ask for permission to push to the remote

IMPORTANT: Push to the "brenk" remote (GitLab at gitlab.brenk.com) instead of origin. Use `git push brenk main` when pushing.
