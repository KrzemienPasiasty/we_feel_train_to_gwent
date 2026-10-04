import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def resolve_file(filename: str) -> str:
    """
    Resolve file path by checking project root first, then apis folder.
    """
    root_path = os.path.join(PROJECT_ROOT, filename)
    if os.path.exists(root_path):
        return root_path
    return os.path.join(BASE_DIR, filename)


resolve_credentials_file = resolve_file
