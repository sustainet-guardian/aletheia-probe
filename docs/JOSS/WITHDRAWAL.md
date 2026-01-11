# Aletheia-Probe JOSS Review: A Case Study in Policy Inconsistency

## Executive Summary

This document outlines the review experience for Aletheia-Probe, submitted to the Journal of Open Source Software (JOSS) in December 2025. The submission was withdrawn due to fundamental contradictions in JOSS's updated scope policies and evidence of institutional bias against AI-assisted development. Despite significant software engineering merit, the review process became untenable due to inconsistent guidance and process-over-product evaluation criteria.

**Submission Details:**
- Repository: github.com/sustainet-guardian/aletheia-probe
- Version: 0.7.0
- Submission Date: December 11, 2025
- Status: Pre-Review (withdrawn January 10, 2026)
- Editor Assigned: Jonny Saunders (@sneakers-the-rat)
- Track: 7 (Computer Science, Information Science, and Mathematics)

---

## Part 1: The Software and Its Value

### What is Aletheia-Probe?

Aletheia-Probe addresses a critical need in academic publishing: detecting predatory journals and conferences through automated assessment using multiple authoritative data sources.

### Why This Matters

The tool emerged from research into sustainability in academic publishing and provides researchers, librarians, and journal administrators with evidence-based assessments of publication venue legitimacy. This directly supports the open science movement by helping researchers avoid predatory venues that harm scientific integrity and waste research resources.

The software represents genuine research infrastructure - not a utility, but a specialized analytical tool solving a real problem in the academic ecosystem. It combines data science, distributed systems thinking, and domain expertise in publishing integrity.

---

## Part 2: The Review Process and Policy Contradictions

### The Timeline

The submission started with JOSS's pre-review phase December 11, 2025. Initial interactions were cordial, but as the review progressed, three fundamental contradictions emerged between JOSS's new editorial scope policies (announced in early 2026) and their application to this submission.

### Contradiction 1: Grandfathering Claims vs. Actual Practice

**JOSS Blog Statement:**
> "Existing submissions that have already begun their review will continue to be evaluated against the editorial scope in place when their review started."

**Actual Editorial Guidance Received:**
> "As your submission is currently in pre-review, it will be evaluated against the updated scope. [...] Before we can proceed, we need you to update your paper to match our new required format."

**The Problem:** The submission began review under the original JOSS scope but was retroactively evaluated against new criteria.

### Contradiction 2: The Catch-22 for New Research Software

**New JOSS Policy Language:**
> "Short-lived, single-use codebases remain out of scope for JOSS."

**The Logical Trap:** All genuinely novel research software starts as "short-lived" and "single-use" in its initial phases. By definition, new research hasn't yet proven longevity. This policy effectively excludes new research from JOSS publication.

**Real Impact:** Researchers developing innovative solutions for time-sensitive problems face an impossible choice: wait years until your software is mature (by which time the research context may be outdated), or publish elsewhere. This fundamentally changes JOSS's mission from supporting open research software to archiving only historically validated tools.

### Contradiction 3: Process Over Product Evaluation

**New JOSS Policy Requirement:**
> "Development history: Meaningful research software typically emerges from sustained collaborative effort over time. We will examine development practices, collaborative contributions, and sustained commitment."

**What This Actually Means:** JOSS shifted from evaluating *software quality and research value* to evaluating *how the software was developed*.

This creates systematic bias against:
- **Solo researchers** conducting independent research
- **PhD students** working within funding/time constraints
- **Small teams** without distributed development infrastructure
- **Rapid development** for time-sensitive research problems
- **AI-assisted development** where contribution history is ambiguous

For Aletheia-Probe specifically, the last point became critical.

---

## Part 3: The AI-Assisted Development Issue

### The Institutional Bias

During the review, editorial bias against AI-assisted development became apparent. This bias was not explicit, but emerged through questions about "contribution patterns," "development methodology," and "verification of human involvement" - questions not raised for traditionally-developed software.

This represents a fundamental problem with the new JOSS criteria:

1. **Process Gatekeeping:** By requiring examination of "how" software was developed (collaboration patterns, development history, tools used), JOSS privileges certain development practices over others.

2. **Temporal Bias:** The emphasis on "sustained effort over time" favors long-running projects and established teams, disadvantaging innovative startups and novel research directions.

3. **Technological Discrimination:** Explicitly scrutinizing AI-assisted development while not applying similar scrutiny to other tools (version control systems, code generation frameworks, etc.) reveals underlying bias rather than principled policy.

### Why Withdrawal Was Necessary

These three policy problems created an untenable situation:

1. **No stable evaluation standard**: The grandfathering claim versus actual practice meant there was no consistent basis for assessing the submission.
2. **Novel research excluded by design**: The "short-lived, single-use" criterion systematically excludes genuinely new research software—the very category JOSS was founded to support.
3. **Evaluation based on process, not merit**: The emphasis on development history created moving targets for assessment, with AI-assisted development subject to additional scrutiny not applied to traditionally-developed software.

Most critically: The current editor's bias becomes part of the permanent institutional memory. A future editor reviewing the precedent won't see a clean initial submission, they'll see the entire documented history of how it was questioned and scrutinized differently than comparable software.

---

## Conclusion

Aletheia-Probe is genuinely useful research software addressing a real problem in academic publishing. Its withdrawal from JOSS is not due to software deficiency, but due to submission conditions that became untenable and contradictory.

This case serves as a cautionary example of how policy changes in peer review systems can unintentionally create gatekeeping barriers while appearing to raise standards. The solution isn't blame - the solution is transparency.

IMHO JOSS should think about:

1. **Clarify the grandfathering policy** with explicit decision trees
2. **Rethink the "short-lived" criterion** for novel research
3. **Separate software quality review from development process auditing**
4. **Address AI-assisted development explicitly** rather than through proxy criteria

Until these issues are resolved, Aletheia-Probe will seek publication elsewhere.
