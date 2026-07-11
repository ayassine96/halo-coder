#!/usr/bin/env python3
"""Shared Git operations for HALO Factory."""

import subprocess


class GitOps:
    """Thin wrapper around git subprocess calls."""

    def __init__(self, repo_dir=None):
        self.repo_dir = repo_dir

    def _git(self, *args, capture=True, check=True):
        cmd = ["git"]
        if self.repo_dir:
            args = ["-C", self.repo_dir] + list(args)
        result = subprocess.run(cmd + list(args), capture_output=capture, text=True)
        if check and result.returncode != 0:
            raise RuntimeError(f"git failed: {result.stderr}")
        return result

    def create_branch(self, branch, base=None):
        """Create and checkout a branch from base (default HEAD)."""
        args = ["checkout", "-b", branch]
        if base:
            args.append(base)
        return self._git(*args)

    def commit(self, message, add=True):
        """Stage all and commit with conventional prefix."""
        if add:
            self._git("add", "-A")
        return self._git("commit", "-m", message)

    def squash_merge(self, branch, message):
        """Squash-merge branch into current branch."""
        self._git("merge", "--squash", branch)
        try:
            self._git("commit", "-m", message, check=True)
        except RuntimeError:
            pass
        return self

    def push(self, remote="origin", ref="main"):
        """Push to remote."""
        return self._git("push", remote, ref)

    def create_tag(self, tag, message=None):
        """Create an annotated tag."""
        args = ["tag", "-a", tag]
        if message:
            args.extend(["-m", message])
        else:
            args.append("-m", tag)
        return self._git(*args)

    def current_branch(self):
        """Return current branch name."""
        result = self._git("rev-parse", "--abbrev-ref", "HEAD")
        return result.stdout.strip()

    def has_changes(self):
        """Return True if working tree has uncommitted changes."""
        result = self._git("status", "--porcelain", check=False)
        return bool(result.stdout.strip())

    def checkout(self, ref):
        """Checkout a ref."""
        return self._git("checkout", ref)