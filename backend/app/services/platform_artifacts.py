"""Bounded platform-owned artifacts. Agent gets workspace/output only, never authority."""
import difflib
import hashlib
import json
import os
import stat
from pathlib import Path
from uuid import UUID
from .repository_scanner import _is_link_or_reparse_point

MAX_FILE = 1_000_000
MAX_TOTAL = 10_000_000
MAX_FILES = 500


def run_directory(run_id):
    from ..core.config import PROJECT_ROOT
    root = Path(os.getenv('PLATFORM_ARTIFACT_ROOT', str(PROJECT_ROOT / '.platform-artifacts')))
    root.mkdir(parents=True, exist_ok=True)
    if _is_link_or_reparse_point(root) or any(_is_link_or_reparse_point(p) for p in root.absolute().parents):
        raise ValueError('Artifact root must not be a link')
    path = root.resolve() / str(UUID(str(run_id)))
    if path.exists() and _is_link_or_reparse_point(path):
        raise ValueError('Run artifact directory must not be a link')
    return path


def read_bytes(path: Path, limit=MAX_FILE):
    if (_is_link_or_reparse_point(path) or not stat.S_ISREG(path.stat().st_mode)
            or path.stat().st_nlink != 1):
        raise ValueError('Artifact must be a regular non-link file')
    with path.open('rb') as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Artifact size exceeded')
    return data


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


def decode_json(data: bytes):
    # Bound nesting before invoking the recursive decoder; strings/escapes are respected.
    depth = 0
    quoted = escaped = False
    text = data.decode('utf-8')
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in '[{':
            depth += 1
            if depth > 24:
                raise ValueError('JSON depth exceeded')
        elif char in ']}':
            depth -= 1
    return json.loads(text, object_pairs_hook=_unique_object,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Invalid JSON number')))


def write_json(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True)


def inventory(root: Path, *, source_repository=False):
    """No silent filtering of agent-created files. Only source repository root .git is excluded."""
    if _is_link_or_reparse_point(root) or not root.is_dir():
        raise ValueError('Unsafe snapshot root')
    result, total, directory_count = {}, 0, 0
    def failed(error):
        raise error
    for current, dirs, files in os.walk(root, followlinks=False, onerror=failed):
        current = Path(current)
        directory_count += 1
        if directory_count > 1000:
            raise ValueError('Too many snapshot directories')
        for name in list(dirs):
            if source_repository and current == root and name == '.git':
                dirs.remove(name)
                continue
            target = current / name
            if _is_link_or_reparse_point(target):
                raise ValueError('Links/reparse points are not supported')
        for name in files:
            if source_repository and current == root and name == '.git':
                continue
            path = current / name
            relative = path.relative_to(root).as_posix()
            data = read_bytes(path)
            total += len(data)
            if len(result) >= MAX_FILES or total > MAX_TOTAL:
                raise ValueError('Snapshot exceeds bounded Python profile')
            result[relative] = data
    return dict(sorted(result.items()))


def check_profile(files):
    """Initial v2 profile: no config discovery, local plugins or secret files."""
    for name in files:
        parts = Path(name).parts
        if (any(part.startswith('.') for part in parts) and name != '.gitignore'
                or Path(name).name in ('conftest.py', 'sitecustomize.py', 'usercustomize.py')
                or (Path(name).suffix not in ('.py', '.md', '.txt') and name != '.gitignore')
                or any(part in ('__pycache__', 'node_modules', 'venv') for part in parts)):
            raise ValueError(f'Unsupported file in fixed Python profile: {name}')
    if not any(name.endswith('.py') for name in files):
        raise ValueError('No Python source')


def python_hash(files):
    hasher = hashlib.sha256(b'RepoPilot-Python-Snapshot-v1\0')
    for name, data in sorted(files.items()):
        if not name.endswith('.py'):
            continue
        encoded = name.encode('utf-8')
        hasher.update(len(encoded).to_bytes(8, 'big') + encoded)
        hasher.update(len(data).to_bytes(8, 'big') + data)
    return hasher.hexdigest()


def file_hashes(files):
    return {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}


def copy_files(files, destination):
    destination.mkdir(parents=True, exist_ok=False)
    for name, data in files.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def compare_files(before, after, editable, protected):
    changed = [name for name in sorted(before.keys() | after.keys()) if before.get(name) != after.get(name)]
    chunks = []
    for name in changed:
        old = before.get(name, b'').decode('utf-8', errors='replace').splitlines(keepends=True)
        new = after.get(name, b'').decode('utf-8', errors='replace').splitlines(keepends=True)
        chunks.extend(difflib.unified_diff(old, new, fromfile=f'a/{name}', tofile=f'b/{name}'))
    diff = ''.join(chunks)
    return dict(changed_files=changed, diff=diff,
                diff_sha256=hashlib.sha256(diff.encode()).hexdigest(),
                diff_within_scope=set(changed) <= set(editable),
                protected_tests_intact=all(before.get(p) == after.get(p) for p in protected))
