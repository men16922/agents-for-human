#!/usr/bin/env python3
"""Deterministic, offline checks for Rehearsal's proposal/configuration baseline."""
from __future__ import annotations

import json
import sys
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
PAGES = ('agents-for-human-propsal.html', 'archive/aftercare/proposal.html')
VOID = set('area base br col embed hr img input link meta param source track wbr'.split())


class Page(HTMLParser):
    def __init__(self, source: str):
        super().__init__(convert_charrefs=True)
        self.ids: list[str] = []
        self.references: list[str] = []
        self.runtime: list[str] = []
        self.labels: list[str] = []
        self.stack: list[str] = []
        self.problems: list[str] = []
        self.headings = Counter()
        self.lang = ''
        self.viewport = False
        self.feed(source)
        self.close()
        if self.stack:
            self.problems.append(f'unclosed tags: {self.stack}')

    def handle_starttag(self, tag, pairs):
        attrs = dict(pairs)
        if tag not in VOID:
            self.stack.append(tag)
        if attrs.get('id'):
            self.ids.append(attrs['id'])
        if attrs.get('href'):
            self.references.append(attrs['href'])
        self.labels.extend(attrs.get('aria-labelledby', '').split())
        if tag in {'h1', 'h2'}:
            self.headings[tag] += 1
        if tag == 'html':
            self.lang = attrs.get('lang', '')
        if tag == 'meta' and attrs.get('name') == 'viewport':
            self.viewport = bool(attrs.get('content'))
        if tag in {'script', 'img', 'iframe', 'source', 'audio', 'video'} and attrs.get('src'):
            self.runtime.append(attrs['src'])
        if tag == 'link' and 'stylesheet' in attrs.get('rel', '').split() and attrs.get('href'):
            self.runtime.append(attrs['href'])

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not self.stack or self.stack[-1] != tag:
            self.problems.append(f'unexpected closing tag: {tag}')
        else:
            self.stack.pop()


def check_page(path: Path, root: Path) -> list[str]:
    path = path.resolve()
    page = Page(path.read_text(encoding='utf-8'))
    errors = list(page.problems)
    if not page.lang or not page.viewport or page.headings['h1'] != 1 or page.headings['h2'] < 1:
        errors.append('expected language, viewport, one h1 and section headings')
    errors.extend(f'duplicate ID: {key}' for key, n in Counter(page.ids).items() if n > 1)
    errors.extend(f'missing aria label target: {key}' for key in page.labels if key not in page.ids)
    for reference in page.references + page.runtime:
        url = urlsplit(reference)
        if url.scheme or url.netloc:
            if reference in page.runtime:
                errors.append(f'external runtime asset: {reference}')
            continue  # External citations are deliberately not fetched.
        destination = (path.parent / unquote(url.path)).resolve() if url.path else path
        if not destination.is_relative_to(root.resolve()) or not destination.is_file():
            errors.append(f'missing or out-of-repo local reference: {reference}')
        elif url.fragment and destination.suffix.lower() == '.html':
            target = page if destination == path else Page(destination.read_text(encoding='utf-8'))
            if unquote(url.fragment) not in target.ids:
                errors.append(f'missing fragment: {reference}')
    return errors


def check_config(root: Path) -> list[str]:
    errors = []
    cfg = json.loads((root / '.claude/harness-config.json').read_text())
    if cfg.get('project_name') != 'Rehearsal / agents-for-human':
        errors.append('project_name does not identify this repository')
    if cfg.get('gate') != 'make check' or cfg.get('smoke') != 'make smoke-local':
        errors.append('gate/smoke must match implemented Make targets')
    if cfg.get('engine') not in cfg.get('engine_choices', []):
        errors.append('engine is not a supported configured choice')
    required = {'brief', 'status', 'plan', 'log', 'completed', 'decisions', 'lessons'}
    if not required.issubset(cfg.get('docs', {})):
        errors.append('required context document paths are missing')
    for key, relative in cfg.get('docs', {}).items():
        path = (root / relative).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            errors.append(f'missing context document: {relative}')
            continue
        text = path.read_text()
        if key != 'lessons' and not text.strip():
            errors.append(f'empty context document: {relative}')
        limit = cfg.get('budgets', {}).get(key)
        if limit is not None and len(text.splitlines()) > limit:
            errors.append(f'document exceeds {limit} lines: {relative}')
    for name in ('scripts/overnight/opencode.json', 'scripts/overnight/antigravity-settings.snippet.json'):
        json.loads((root / name).read_text())
    permissions = json.loads((root / 'scripts/overnight/overnight-settings.json').read_text())['permissions']
    for target in ('check', 'smoke-local', 'overnight-where'):
        if f'Bash(make {target})' not in permissions['allow']:
            errors.append(f'missing Claude gate permission: {target}')
    if 'Bash(make *)' in permissions['allow']:
        errors.append('blanket make permission is forbidden')
    for command in ('git push*', 'make deploy*', 'make serve*', 'make infra-*', 'aws *'):
        if f'Bash({command})' not in permissions['deny']:
            errors.append(f'missing unattended deny: {command}')
    # Syntax/schema check only; engine enforcement is not claimed by this check.
    rules = []
    def prefix_rule(**rule):
        if rule.get('decision') not in {'allow', 'prompt', 'forbidden'} or not rule.get('pattern'):
            errors.append('invalid Codex prefix rule')
        rules.append(rule)
    exec(compile((root / '.codex/rules/overnight.rules').read_text(), 'overnight.rules', 'exec'),
         {'__builtins__': {}, 'prefix_rule': prefix_rule})
    if not any(r.get('pattern') == ['git', 'push'] and r.get('decision') == 'forbidden' for r in rules):
        errors.append('missing Codex push boundary')
    return errors


def main(root: Path = ROOT) -> int:
    errors = []
    for name in PAGES:
        try:
            errors.extend(f'{name}: {error}' for error in check_page(root / name, root))
        except (OSError, ValueError) as exc:
            errors.append(f'{name}: {exc}')
    try:
        errors.extend(check_config(root))
    except (OSError, ValueError, KeyError, TypeError, SyntaxError, NameError) as exc:
        errors.append(f'configuration: {exc}')
    if errors:
        for error in errors:
            print(f'FAIL: {error}', file=sys.stderr)
        return 1
    print(f'PASS: {len(PAGES)} HTML documents; local references; harness configuration; context paths/budgets.')
    print('Scope: offline document/configuration integrity, not product, browser or AWS behavior.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
