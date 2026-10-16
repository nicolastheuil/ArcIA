#!/usr/bin/env python3
"""Check tracked first-party documentation without reading local private drafts."""
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def tracked_paths():
    return set(subprocess.check_output(
        ['git', 'ls-files', '-z'], cwd=ROOT).decode('utf-8').split('\0')) - {''}


def markdown_paths(paths):
    return sorted(p for p in paths if p.endswith('.md') and
                  not p.startswith('deploy/hermes/skills/'))


def without_code(content):
    # Exclude examples/fenced code, but keep links whose label contains backticks.
    return re.sub(r'^```[^\n]*\n.*?^```\s*$', '', content, flags=re.M | re.S)


def anchors(content):
    result = set(re.findall(r'<a\s+id=["\']([^"\']+)', content))
    counts = {}
    for heading in re.findall(r'^#{1,6}\s+(.+?)\s*#*$', without_code(content), re.M):
        heading = re.sub(r'\[([^]]+)\]\([^)]+\)', r'\1', heading)
        slug = re.sub(r'[^\w\- ]', '', heading.lower()).replace(' ', '-')
        index = counts.get(slug, 0)
        counts[slug] = index + 1
        result.add(slug + (f'-{index}' if index else ''))
    return result


def validate():
    paths = tracked_paths()
    docs = markdown_paths(paths)
    errors = []
    count = 0
    cache = {}
    for source in docs:
        content = (ROOT / source).read_text(encoding='utf-8')
        if source.startswith('docs/handoff-'):
            errors.append(f'{source}: HANDOFF_MUST_BE_ARCHIVED')
        for target in re.findall(r'\]\(([^\s)]+)\)', without_code(content)):
            url = urlsplit(target)
            if url.scheme or url.netloc:
                continue
            resolved = ((ROOT / source).parent / unquote(url.path)).resolve() if url.path else (ROOT / source).resolve()
            if not resolved.is_relative_to(ROOT.resolve()):
                errors.append(f'{source}: LINK_OUTSIDE_REPOSITORY {target}')
                continue
            relative = resolved.relative_to(ROOT.resolve()).as_posix()
            # Existence alone must not allow links to an untracked private file.
            if relative not in paths and not any(p.startswith(relative.rstrip('/') + '/') for p in paths):
                errors.append(f'{source}: LINK_TARGET_NOT_TRACKED {target}')
                continue
            if url.fragment and resolved.suffix == '.md':
                if relative not in cache:
                    cache[relative] = anchors(resolved.read_text(encoding='utf-8'))
                if unquote(url.fragment) not in cache[relative]:
                    errors.append(f'{source}: LINK_ANCHOR_MISSING {target}')
            count += 1
    for folder in ('guides', 'runbooks', 'annexes'):
        index = 'docs/README.md'
        content = (ROOT / index).read_text(encoding='utf-8')
        for source in docs:
            if source.startswith(f'docs/{folder}/') and source != index and Path(source).name not in content:
                errors.append(f'{index}: DOCUMENT_NOT_INDEXED {source}')
    if errors:
        raise ValueError('\n'.join(errors))
    return f'DOCUMENTATION_VERIFIED files={len(docs)} local_links={count}'


if __name__ == '__main__':
    print(validate())
