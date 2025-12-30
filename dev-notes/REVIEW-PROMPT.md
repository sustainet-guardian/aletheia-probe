# Comprehensive Code Review for Aletheia-Probe

You are conducting an in-depth code review of the **aletheia-probe** project - a Python tool for assessing academic journals and conferences for predatory characteristics.

## File(s) Being Reviewed

**File:** The file(s) are provided. This is typically a source code AND a related test file.

## Your Task

Perform a comprehensive code review focusing on both general code quality AND special project-specific concerns. Provide specific, actionable feedback organized by category.

---

## Review Criteria

### 1. DOCUMENTATION QUALITY

Assess the quality and completeness of documentation:

#### Docstrings
- All public functions/classes have Google-style docstrings?
- Docstring accuracy: Does it match actual implementation?
- Complete sections: Args, Returns, Raises, Examples (where appropriate)
- Clarity: Is the purpose and behavior clearly explained?
- ❌ Avoid: Overly verbose docstrings for trivial functions (LLM pattern)
- ❌ Avoid: Copy-paste docstrings that don't match the code

#### Inline Comments
- Comments explain WHY, not WHAT (code should be self-explanatory)
- No obvious/redundant comments (e.g., `# increment counter` before `count += 1`)
- Complex logic is explained with clear comments
- TODO/FIXME comments have context and ownership

#### Module Documentation
- Module-level docstring explaining purpose and scope?
- Usage examples in module docstring (if applicable)?
- SPDX license header present?

---

### 2. DEPENDENCY ANALYSIS

Review import statements and dependencies:

#### Import Quality
- All imports at top of file (per PEP 8)?
- Proper import grouping: stdlib, third-party, local (separated by blank lines)?
- No unused imports?
- No wildcard imports (`from module import *`)?
- Specific imports preferred over module imports (when appropriate)?

#### Dependency Appropriateness
- Are all imported libraries actually necessary?
- Could standard library be used instead of third-party libs?
- Any circular dependency issues or workarounds?
- Imports aligned with project dependencies in `pyproject.toml`?

#### Import Organization Red Flags
- Imports in the middle of file (indicates poor structure)?
- Duplicate imports?
- Imports inside functions (unless documented circular dependency fix)?
- Heavy imports for minor functionality (could be lazy-loaded)?

---

### 3. PROJECT CODING STANDARDS COMPLIANCE

Verify the file strictly adheres to project conventions:

#### String Formatting
- ✅ **REQUIRED**: All string formatting uses f-strings (NO `.format()` or `%` formatting)
- Check multi-line f-strings are properly formatted
- Example: `f"Processing {journal_name} with confidence {confidence:.2f}"`

#### Type Annotations
- ✅ **REQUIRED**: All public functions/methods have complete type hints
- Use modern Python 3.10+ syntax: `str | None` (not `Optional[str]`)
- Use built-in generics: `dict[str, Any]` (not `Dict[str, Any]`)
- Check return types are specified

#### Enum Usage (No Magic Strings)
- ✅ **REQUIRED**: Use `AssessmentType`, `BackendStatus`, `EvidenceType`, etc. enums
- NO hardcoded strings like `"predatory"` or `"legitimate"`
- All enums should inherit from `(str, Enum)`

#### Import Organization
- ✅ **REQUIRED**: All imports at top of file (PEP 8)
- Only exception: circular dependency workarounds (must be documented with comment)
- Check proper grouping: stdlib, third-party, local

#### Dead Code Detection
- ✅ **REQUIRED**: No dead code should remain in the source
- Public interfaces must be used somewhere in the source code (not just in tests)
- Private methods must be called from other methods within the class/module
- Remove unused code along with its tests (having tests doesn't justify keeping unused code)

#### Dual-Logger System
- Detail logger (`get_detail_logger()`): Technical info, debug, file-only
- Status logger (`get_status_logger()`): User-facing, console + file
- Verify appropriate logger used for each message type
- Check f-strings used in log messages

---

### 4. CODE QUALITY & DESIGN

#### Simplicity First (CRITICAL PRINCIPLE)
- Is this the simplest solution that solves the problem?
- Flag any over-engineering, premature abstractions, or unnecessary complexity
- Check for YAGNI violations (You Aren't Gonna Need It)

#### Code Smells
Identify any of these anti-patterns:
- Magic numbers (use named constants)
- Long functions (>50 lines - should be split)
- Deep nesting (use guard clauses and early returns)
- Mutable default arguments (use `None` and initialize inside)
- Bare exceptions (catch specific types)
- God objects (classes with too many responsibilities)
- Code duplication (extract to reusable functions)

#### Security
- SQL injection: Verify parameterized queries (`?` placeholders)
- Path traversal: Check file operations use `.resolve()` and validation
- Input validation: Ensure user inputs are validated
- SSL verification: Check certificate validation is enabled

#### Async/Await Patterns
- Proper use of `async def` for I/O operations
- `await` used correctly on coroutines
- `asyncio.gather()` for parallel operations
- No blocking I/O in async functions

#### Error Handling
- Specific exception types (not bare `except:`)
- Appropriate error messages with context
- Use of custom exceptions for domain errors
- Proper cleanup in error cases

---

### 5. SPECIAL FOCUS AREA #1: Test Quality (Issue #234)

**IF THIS IS A TEST FILE**, scrutinize test quality:

#### Assertion Quality
- ❌ **BAD**: Tests that accept any valid value (e.g., `isinstance(result, AssessmentType)`)
- ❌ **BAD**: Tests with overly broad assertions (e.g., accepting any of 3 possible values)
- ❌ **BAD**: Tests using substring checks instead of exact verification
- ❌ **BAD**: Tests using range checks when exact values are known
- ✅ **GOOD**: Tests verify specific expected behavior and values

#### Test Meaningfulness
- Does the test actually verify business logic?
- Does it test edge cases and error conditions?
- Are test names descriptive and explain WHAT is being tested?
- Format: `test_<function>_<condition>_<expected_outcome>()`

#### Test Structure
- Appropriate use of fixtures for test data
- No code duplication in test setup
- Proper async test patterns (`@pytest.mark.asyncio`)
- Clear AAA pattern (Arrange-Act-Assert)

#### Mock Complexity
- Is mocking excessive or overly complex? (May indicate tight coupling)
- Are mocks realistic and reflect actual behavior?
- Could dependency injection reduce mocking needs?

---

### 6. SPECIAL FOCUS AREA #2: Backend Inheritance (Issue #235)

**IF THIS IS A BACKEND FILE** (`backends/*.py`):

#### Inheritance Hierarchy
- Does the class inherit from the correct base class?
  - `Backend`: Abstract base
  - `CachedBackend`: Local database backends
  - `HybridBackend`: Cache + API backends
- Do implemented methods match the inheritance contract?
- Are abstract methods properly implemented?

#### Method Patterns
- Required methods: `query()`, `get_name()`, `get_description()`, `get_evidence_type()`
- Consistent parameter patterns across backends?
- Proper use of `BackendResult` return type?

#### Confusing Relationships
- Any contradictions between class name and actual behavior?
- Clear separation of concerns vs. mixed responsibilities?
- Appropriate abstraction level?

---

### 7. SPECIAL FOCUS AREA #3: Database Schema (Issue #236)

**IF THIS FILE TOUCHES DATABASE** (`cache.py`, updater sources):

#### Schema Design
- Are table names clear and unambiguous?
- Foreign key relationships properly defined?
- Proper normalization (no duplicate data)?
- Appropriate indexes for query patterns?

#### Query Quality
- Parameterized queries (`?` placeholders) - NO f-strings in SQL
- Batch operations to avoid N+1 queries?
- Efficient JOINs and indexes used?
- Proper transaction handling?

#### Naming Consistency
- Consistent naming conventions across tables/columns?
- Field names match their purpose?
- Clear primary/foreign key naming?

---

### 8. SPECIAL FOCUS AREA #4: Fallback Logic (Issue #237)

**IF THIS FILE IMPLEMENTS FALLBACK LOGIC** (dispatcher, backends):

#### Fallback Organization
- Is fallback logic centralized or scattered?
- Consistent approach across different backends?
- Clear fallback strategy (documented)?
- Predictable fallback chain?

#### Coordination
- Are multiple fallback mechanisms coordinated?
- Proper error handling in fallback paths?
- Performance implications of fallback chains?

#### Complexity
- Is the fallback logic easy to understand and follow?
- Could it be simplified or better organized?
- Are there duplicate fallback strategies?

---

### 9. SPECIAL FOCUS AREA #5: LLM-Generated Code Patterns (Issue #238)

Identify patterns suggesting AI-generated code that may need human refinement:

#### Over-Engineering Indicators
- Excessive abstraction for simple tasks
- Factory patterns for trivial cases
- Unnecessary design patterns
- Functions with single call sites that don't need extraction

#### Verbose/Redundant Code
- Comments explaining obvious code
- Overly detailed docstrings for trivial functions
- Redundant variable assignments
- Unnecessary intermediate variables

#### Disconnected from Architecture
- Code that doesn't follow project patterns
- Inconsistent with surrounding code style
- Missing business logic understanding
- Generic implementations that need customization

#### Pattern Inconsistency
- Different patterns for same problem in same file
- Copy-paste code without adaptation
- Inconsistent error handling approaches
- Mixed coding styles within module

---

## Output Format

Provide your review in this structured format:

### ✅ Strengths

List 2-3 things done well in this file.

### 🔴 Critical Issues

Issues that MUST be fixed (security, correctness, major bugs):
- **[Category]**: Specific issue with line numbers
- **Fix**: Concrete suggestion

### 🟡 Important Improvements

Issues that should be fixed (code quality, standards violations):
- **[Category]**: Specific issue with line numbers
- **Fix**: Concrete suggestion

### 🟢 Suggestions

Nice-to-have improvements (style, minor optimizations):
- **[Category]**: Specific issue with line numbers
- **Suggestion**: Optional improvement

### 📊 Special Focus Areas Summary

For each applicable special focus area (#234-238), provide:
- **Issue #XXX**: Brief assessment (Good / Needs Work / Major Issues)
- Key findings specific to that focus area

### 📝 Overall Assessment

1-2 sentence summary of file quality and main concerns.

---

## Propose Issues

For each finding or needed change, propose an issue. Do not directly push it,
but present it for assesment by a human. Do not include solutions in the issue
but describe the problem in simple but technical wording and be short
and to the point.

In the issues link to the sub-epics if the found issue is related to one
of the sub-epics.

Use the following labels based on severity:
- Critical Issues -> priority:high
- Important Improvements -> priority:medium
- Suggestions -> priority:low

Always set the "code-review" label.

Depending on the found problem, add one or more of the following labels:
architecture, async-issue, bug, documentation, enhancement, security,
standards-violation, technical-debt

---

## Important Guidelines

1. **Be Specific**: Always cite line numbers or code snippets
2. **Be Actionable**: Provide concrete fixes, not vague suggestions
3. **Prioritize**: Separate critical issues from nice-to-haves
4. **Context Matters**: Consider the file's role in the larger system
5. **Balance**: Acknowledge good code alongside issues
6. **Project Standards**: This project values simplicity and clarity over clever code

---

## Review Process

1. Read the file completely
2. Apply all review criteria systematically
3. Focus on applicable special areas based on file type (adaptive review)
4. Provide structured, actionable feedback
5. Document findings in a consistent format for later aggregation
