# Contributing to Journal Assessment Tool

Thank you for your interest in contributing! This guide will help you get started with development and contribution workflow.

## Development Setup

### Prerequisites
- Python 3.9 or higher
- Git
- Virtual environment tool (venv/conda)

### Quick Setup
```bash
# 1. Fork and clone
git clone https://github.com/yourusername/aletheia-probe.git
cd aletheia-probe

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install in development mode
pip install -e ".[dev]"

# 4. Run tests to verify setup
bash scripts/run-quality-checks.sh
```

## Development Workflow

### 1. Create Feature Branch
```bash
git checkout -b feature/your-feature-name
```

### 2. Make Changes
- Write code following the style guidelines below
- Add tests for new functionality
- Update documentation if needed

### 3. Quality Checks
```bash
# Format code
black src/ tests/

# Check linting
ruff check src/ tests/

# Type checking
mypy src/

# Run tests
pytest tests/ --cov=src

# All of them above
bash scripts/run-quality-checks.sh
```

### 4. Commit Changes
```bash
git add .
git commit -m "feat: add your feature description"
```

### 5. Push and Create PR
```bash
git push origin feature/your-feature-name
```

Then create a Pull Request on GitHub.

## Code Style Guidelines

### Python Style
- Follow PEP 8
- Use type hints for all functions
- Maximum line length: 88 characters (Black default)
- Use descriptive variable names
- Add docstrings for classes and functions
- **REQUIRED**: Include SPDX license identifier at the top of every Python file

### SPDX License Requirements

All Python source files must include an SPDX license identifier for licensing clarity and compliance:

**For files without shebang lines:**
```python
# SPDX-License-Identifier: MIT
"""Module docstring here."""
```

**For script files with shebang:**
```python
#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Script docstring here."""
```

**Why SPDX identifiers are required:**
- Provides machine-readable licensing information
- Aligns with Python packaging standards (PEP 639)
- Enables automated license compliance checking
- Improves clarity for contributors and users

The SPDX check runs automatically in CI/CD and can be tested locally:
```bash
python scripts/check-spdx.py
```

### Commit Messages
Use conventional commit format:
```
type(scope): description

feat(backend): add DOAJ integration
fix(cli): handle empty input properly
docs(readme): update installation instructions
test(models): add validation tests
```

## Testing

### Test Structure
- Unit tests: `tests/unit/`
- Integration tests: `tests/integration/`
- Fixtures: `tests/conftest.py`

### Writing Tests
```python
import pytest
from aletheia_probe.models import QueryInput

def test_query_input_validation():
    query = QueryInput(raw_input="Journal of Testing")
    assert query.raw_input == "Journal of Testing"

@pytest.mark.asyncio
async def test_backend_query():
    # Test async functionality
    pass
```

### Coverage Requirements
- Minimum 80% overall coverage
- Core modules (models, backends, dispatcher): 90%+
- New features must include tests
- Tests should cover edge cases and error conditions

## Documentation

### Adding Documentation
- User-facing docs: `docs/`
- Development notes: `dev-notes/`
- API documentation: Use docstrings
- Configuration examples: `docs/configuration.md`

### Docstring Format
```python
def assess_journal(name: str, issn: Optional[str] = None) -> AssessmentResult:
    """Assess journal legitimacy using multiple backends.

    Args:
        name: Journal name to assess
        issn: Optional ISSN for more accurate matching

    Returns:
        Assessment result with confidence score and reasoning

    Raises:
        ValidationError: If input is invalid
        TimeoutError: If backends don't respond
    """
```

## Adding New Backends

### Backend Interface
All backends must inherit from `Backend` class:

```python
from aletheia_probe.backends.base import Backend
from aletheia_probe.models import BackendResult, QueryInput

class MyBackend(Backend):
    def get_name(self) -> str:
        return "MyBackend"

    def get_description(self) -> str:
        return "Description of what this backend checks"

    async def query(self, query_input: QueryInput) -> BackendResult:
        # Implementation here
        pass
```

### Registration
Register your backend in `__init__.py`:
```python
from .my_backend import MyBackend
backend_registry.register(MyBackend())
```

### Advanced Backend Types
For more complex backends, consider using these specialized base classes:

- **CachedBackend**: Automatically caches backend results to improve performance and reduce API calls
- **HybridBackend**: Combines multiple data sources or backends into a single unified backend

These can be found in the `aletheia_probe.backends` module and provide additional functionality beyond the basic `Backend` class.

## Project Structure

### Core Components
- **Models**: Pydantic data models for type safety
- **Backends**: Pluggable assessment sources
- **Normalizer**: Input cleaning and validation
- **Dispatcher**: Assessment coordination and scoring
- **Cache**: Performance optimization
- **CLI**: Command-line interface

### Data Sources
For a list of current backends check `aletheia_probe.backends`.

## Release Process

### Version Management
- Use semantic versioning (semver.org)
- Update version in `pyproject.toml`
- Update `CHANGELOG.md`

### Release Checklist
- [ ] All tests passing
- [ ] Documentation updated
- [ ] Version bumped
- [ ] Changelog updated
- [ ] Tagged release created
- [ ] PyPI package published

## AI-Assisted Development

**This project encourages the use of AI coding agents.** See the [README](../../README.md#ai-assisted-development) for guidelines.

Key points for contributors:
- Review and test all AI-generated code thoroughly
- Follow project standards in [AGENTS.md](../../AGENTS.md)
- Optionally tag commits/PRs with `[AI-assisted]` for transparency
- You are responsible for all submitted code

## Getting Help

### Development Questions
- Check existing [Issues](https://github.com/sustainet-guardian/aletheia-probe/issues)
- Create new issue with `question` label
- Review development notes in `dev-notes/`

### Communication
- Be respectful and constructive
- Focus on technical merit
- Provide context for suggestions
- Test your changes thoroughly

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

## Recognition

Contributors are recognized in:
- GitHub contributors list
- Release notes
- Project acknowledgments

Thank you for helping improve journal assessment tools for the academic community!
