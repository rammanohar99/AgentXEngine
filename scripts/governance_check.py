#!/usr/bin/env python3
"""
Governance Enforcement Automation.

Checks documentation for:
- Valid YAML metadata frontmatter
- Valid ownership and lifecycle fields
- Stale documentation (last_reviewed > 180 days)
- Broken internal Markdown links
- Orphaned ADRs (not linked in docs/adr/README.md)
"""

import os
import re
import sys
import yaml
from datetime import datetime, timedelta
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).parent.parent
DOCS_DIR = WORKSPACE_ROOT / "docs"

REQUIRED_FRONTMATTER = ["title", "domain", "doc_type", "status", "owner", "last_reviewed"]
VALID_STATUS = ["active", "deprecated", "archived", "proposed", "accepted", "superseded", "planned"]

STALE_DAYS_LIMIT = 180


def parse_frontmatter(file_path: Path) -> tuple[dict, str]:
    """Extract YAML frontmatter and the rest of the text."""
    try:
        content = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return {}, ""
        
    if not content.startswith("---\n"):
        return {}, content

    parts = content.split("---\n", 2)
    if len(parts) < 3:
        return {}, content

    try:
        frontmatter = yaml.safe_load(parts[1])
        return frontmatter if isinstance(frontmatter, dict) else {}, parts[2]
    except yaml.YAMLError:
        return {}, content


def check_metadata(file_path: Path, frontmatter: dict) -> list[str]:
    """Validate document metadata."""
    errors = []
    
    # Exceptions: Archive docs and index READMEs might be looser, but let's check basic structure
    if not frontmatter:
        # Ignore root README and template files
        if file_path.name in ["README.md", "TEMPLATE.md", "AGENTS.md", "SKILLS.md"] or "archive" in file_path.parts:
            return []
        if file_path.parent == WORKSPACE_ROOT:
            return []
        return [f"{file_path.relative_to(WORKSPACE_ROOT)}: Missing or invalid YAML frontmatter."]

    # Ignore TEMPLATE files even if they have frontmatter
    if file_path.name == "TEMPLATE.md":
        return []

    for field in REQUIRED_FRONTMATTER:
        if field not in frontmatter:
            errors.append(f"{file_path.relative_to(WORKSPACE_ROOT)}: Missing required field '{field}'.")

    status = frontmatter.get("status", "")
    if status and status not in VALID_STATUS:
        errors.append(f"{file_path.relative_to(WORKSPACE_ROOT)}: Invalid status '{status}'. Expected one of {VALID_STATUS}.")

    last_reviewed = frontmatter.get("last_reviewed")
    if last_reviewed:
        try:
            if isinstance(last_reviewed, str):
                review_date = datetime.strptime(last_reviewed, "%Y-%m-%d").date()
            else:
                review_date = last_reviewed
            if (datetime.now().date() - review_date).days > STALE_DAYS_LIMIT:
                errors.append(f"{file_path.relative_to(WORKSPACE_ROOT)}: Document is stale (last_reviewed {last_reviewed} > {STALE_DAYS_LIMIT} days ago).")
        except ValueError:
            errors.append(f"{file_path.relative_to(WORKSPACE_ROOT)}: Invalid last_reviewed format '{last_reviewed}'. Expected YYYY-MM-DD.")

    return errors


def check_broken_links(file_path: Path, content: str) -> list[str]:
    """Find relative markdown links that point to missing files."""
    errors = []
    # Match markdown links: [text](path)
    link_pattern = re.compile(r"\[.*?\]\((?!http|https|mailto|ftp)(.*?)\)")
    
    for match in link_pattern.finditer(content):
        link_path = match.group(1).split("#")[0].strip() # ignore fragments
        if not link_path:
            continue
            
        # Ignore common template placeholders
        if "NNN" in link_path or "path/to" in link_path or "relevant.md" in link_path:
            continue
            
        target = (file_path.parent / link_path).resolve()
        
        # Don't check links outside the workspace just in case
        try:
            target.relative_to(WORKSPACE_ROOT)
        except ValueError:
            continue

        if not target.exists():
            errors.append(f"{file_path.relative_to(WORKSPACE_ROOT)}: Broken link to '{link_path}'.")

    return errors


def check_orphaned_adrs() -> list[str]:
    """Ensure all ADRs in docs/adr/ are linked in docs/adr/README.md."""
    adr_dir = DOCS_DIR / "adr"
    adr_index = adr_dir / "README.md"
    
    if not adr_index.exists():
        return []
        
    index_content = adr_index.read_text(encoding="utf-8")
    errors = []
    
    for adr_file in adr_dir.glob("*.md"):
        if adr_file.name in ["README.md", "TEMPLATE.md"]:
            continue
            
        if adr_file.name not in index_content:
            errors.append(f"docs/adr/{adr_file.name}: Orphaned ADR. Not linked in docs/adr/README.md.")
            
    return errors


def main() -> int:
    all_errors = []
    
    # 1. Check Metadata and Broken Links
    for root, dirs, files in os.walk(WORKSPACE_ROOT):
        # Ignore some dirs
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ["node_modules", "dist", "build", "__pycache__"]]
        
        for file in files:
            if not file.endswith(".md"):
                continue
                
            file_path = Path(root) / file
            
            # Skip checking auto-generated docs or third-party
            if "node_modules" in file_path.parts:
                continue

            frontmatter, content = parse_frontmatter(file_path)
            
            # Check metadata (only strongly enforced inside docs/)
            if DOCS_DIR in file_path.parents:
                all_errors.extend(check_metadata(file_path, frontmatter))
                
            # Check broken links
            all_errors.extend(check_broken_links(file_path, content))

    # 2. Check Orphaned ADRs
    all_errors.extend(check_orphaned_adrs())

    if all_errors:
        print(f"Governance Check Failed: {len(all_errors)} violations found.\n")
        for err in all_errors:
            print(f"❌ {err}")
        return 1

    print("✅ Governance Check Passed: All docs comply with metadata and lifecycle standards.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
