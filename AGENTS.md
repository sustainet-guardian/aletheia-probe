# AI Coding Agent Guidelines

**Project:** Aletheia-Probe - Journal and Conference Assessment Tool
**Purpose:** Explicit instructions for AI coding assistants
**Supported Agents:** All AI coding assistants

**Note:** This project actively encourages the use of AI coding agents in development. Your contributions are valued as tools to aid problem-solving, code generation, review, and learning.

---

## 0. Agent Communication Guidelines

**IMPORTANT:** Follow these communication rules:

- **NEVER** mention your specific agent name (Claude, Gemini, etc.) in commits, PRs, or code
- **NEVER** add co-author attribution for AI agents
- **DO** use the tag `[AI-assisted]` when appropriate in comments or PR descriptions
- Focus on the technical content, not the tool used to create it

---

## 1. Development Process Workflow

Follow this process for ALL development work:

### Step-by-Step Workflow

1. **Start from main branch**
   ```bash
   git checkout main
   git pull origin main
   ```

2. **Identify the task**
   - Observe what needs to be done (typically: resolve an issue)
   - Review the issue details and requirements

3. **Create a feature branch**
   ```bash
   git checkout -b fix-issue-<number>-<description>
   ```

4. **Develop, fix, and test**
   - Make your changes following all coding standards
   - Write or update tests as needed
   - Test locally during development

5. **Run all tests**
   ```bash
   bash scripts/run-quality-checks.sh
   ```
   - ALL checks MUST pass before proceeding

6. **Commit your changes**
   - Follow conventional commit format
   - Write clear commit messages explaining WHY the changes were made

7. **Create a Pull Request**
   - Push your branch to GitHub
   - Create PR with proper description (see section 4 below)
   - Link the PR to the issue

8. **Review cycle**
   - Human reviewer will provide feedback
   - If there are comments or requested changes: **Go back to step 4**
   - Address all feedback and repeat steps 4-7 as needed

9. **Post-merge cleanup**
   - After PR is merged, run cleanup script:
   ```bash
   ./scripts/post-pr-merge.sh
   ```
   - This cleans up everything locally and prepares for next task

---

## 2. Before Making ANY Changes (MANDATORY)

Read and follow ALL standards in:

- **`dev-notes/CODING_STANDARDS.md`** - All coding conventions, patterns, code smells to avoid
- **`dev-notes/LOGGING_USAGE.md`** - Dual-logger system usage
- **`dev-notes/DEPENDENCIES.md`** - Dependencies information
- **`dev-notes/NORMALIZED_DATABASE_DESIGN.md`** - Database schema (if working with data)
- **`dev-notes/integration/*.md`** - Data sources (if working with backends)

Also:
- Review recent commits to understand current patterns
- Check open issues and PRs for ongoing work
- Remember: This tool affects real academic decisions - quality is paramount

---

## 3. Pre-Commit Workflow (MANDATORY)

Before ANY commit, run:

```bash
bash scripts/run-quality-checks.sh
```

**Requirements:**
- ALL checks MUST pass
- Do NOT commit failing code
- Do NOT bypass checks
- Do NOT use `type: ignore` without justification

---

## 4. Commit and PR Format

### Commits

Follow conventional commits (see `git log` for examples):

```
<type>: <subject ≤72 chars>

<WHY, not just WHAT>
```

Types: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`

### Pull Requests

Include:
- **Summary**: What does this do?
- **Motivation**: Why is this needed?
- **Testing**: How was this tested?
- **Checklist**: Quality checks pass, tests added, docs updated

---

## 5. Summary Checklist

✅ **DO:**
1. Read all `dev-notes/` documentation first
2. Run `bash scripts/run-quality-checks.sh` before committing
3. Follow CODING_STANDARDS.md (simplicity, f-strings, type hints, enums, etc.)
4. Follow LOGGING_USAGE.md (dual-logger system)
5. Write tests for new functionality
6. Add docstrings (Google style)
7. Write clear commit messages explaining WHY

❌ **DO NOT:**
1. Commit code that fails quality checks
2. Modify code you don't understand
3. Introduce code smells (see CODING_STANDARDS.md)
4. Add unnecessary dependencies
5. Use backwards-compatibility hacks

**When uncertain, ask for clarification.**

---

## 6. Git and Version Control Guidelines

**IMPORTANT Git Rules:**
- **ALWAYS** use specific filenames when adding to git, NEVER use patterns or directories
- **NEVER** reference any specific agent name (Claude, Gemini, etc.) in commit messages
- **NEVER** reference any agent name in any part of source code or documentation
- **DO** use `[AI-assisted]` tag when appropriate in commit messages

---

## 7. GitHub PR Comment Replies

To reply to PR review comments on GitHub:

```bash
# Reply to a specific review comment using the comment ID
gh api --method POST repos/{owner}/{repo}/pulls/{pr_number}/comments/{comment_id}/replies --field body="Your reply message [AI-assisted]"

# Example:
gh api --method POST repos/sustainet-guardian/aletheia-probe/pulls/28/comments/2544706229/replies --field body="Fixed! Removed the unrelated cache TTL entry from the changelog. [AI-assisted]"
```

**Important notes:**
- Use the `/replies` endpoint to reply to existing review comments
- The `comment_id` must be a top-level review comment (not a reply to a reply)
- Always include the `[AI-assisted]` tag in replies
- Find comment IDs using: `gh api repos/{owner}/{repo}/pulls/{pr_number}/comments`
