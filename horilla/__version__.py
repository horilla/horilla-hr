"""Single source of truth for the Horilla HR product version.

Keep in lockstep with release tags: the Docker publish workflow asserts that
this string matches the git tag being built, so a mismatch fails the release
rather than shipping an image whose label disagrees with its tag.
"""

__version__ = "2.1.1"
