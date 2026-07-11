#!/usr/bin/env python3
"""Git operations for HALO Factory state transitions (GIT-R2..R5).

- Create branch agent/{spec_id} (GIT-R4)
- Conventional commit prefixes (GIT-R2)
- Squash-merge with AC in commit body (GIT-R5)
- Snapshot/restore via Git tags (REL-5)
"""

import re
from halo.common.git_utils import GitOps


class SpecGitOps:
    """Git operations specific to spec lifecycle."""

    def __init__(self, repo_dir=None):
        self.git = GitOps(repo_dir)

    def create_spec_branch(self, spec_id):
        """Create branch agent/{spec_id} from main (GIT-R4)."""
        branch = f"agent/{spec_id}"
        self.git.create_branch(branch, base="main")
        return branch

    def commit_transition(self, spec_id, action, extra=""):
        """Commit with conventional prefix (GIT-R2).

        Examples:
            agent: start SPEC-001
            agent: plan SPEC-001
            human: approve SPEC-001
        """
        msg = f"{action} {spec_id}"
        if extra:
            msg += f" — {extra}"
        self.git.commit(msg)
        return msg

    def squash_merge_spec(self, spec_id, acceptance_criteria=""):
        """Squash-merge agent/{spec_id} to main with AC in body (GIT-R5)."""
        self.git.checkout("main")
        msg = f"Merge {spec_id}"
        if acceptance_criteria:
            msg += f"\n\nAcceptance Criteria:\n{acceptance_criteria}"
        self.git.squash_merge(f"agent/{spec_id}", msg)
        return msg

    def create_snapshot(self, tag=None):
        """Create a snapshot tag for project state (REL-5)."""
        from datetime import datetime, timezone
        if tag is None:
            tag = f"halo-snapshot-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        self.git.create_tag(tag, message=f"HALO Factory snapshot {tag}")
        return tag

    def restore_snapshot(self, tag):
        """Restore project state from a snapshot tag (REL-5)."""
        self.git.checkout(tag)
        return tag

    def delete_spec_branch(self, spec_id):
        """Delete the agent/{spec_id} branch after merge."""
        branch = f"agent/{spec_id}"
        result = self.git._git("branch", "-D", branch, check=False)
        return result.returncode == 0