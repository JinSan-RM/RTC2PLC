"""Portable Specim Lumo camera kit version metadata."""

__version__ = "0.2.0"
VERSION = __version__
BUILD_DATE = "2026-06-11"
GIT_COMMIT = "9ca52ae"
GIT_DESCRIBE = "9ca52ae-dirty"


def version_payload() -> dict[str, str]:
    return {
        "version": VERSION,
        "build_date": BUILD_DATE,
        "git_commit": GIT_COMMIT,
        "git_describe": GIT_DESCRIBE,
    }
