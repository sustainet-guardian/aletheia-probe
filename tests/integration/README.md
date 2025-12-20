# Integration Tests

## What Are Integration Tests?

Integration tests verify that multiple components work together correctly. Unlike unit tests which test isolated functions with mocks, these tests:

- Test real component interactions (Normalizer → Dispatcher → Backends → Assessor)
- May make real external API calls (marked `@pytest.mark.requires_network`)
- Validate complete workflows (BibTeX processing, batch assessments, end-to-end pipelines)

## Key Differences from Unit Tests

| Unit Tests | Integration Tests |
|------------|-------------------|
| Single function/class | Multiple components |
| Mocked dependencies | Real or partial mocks |
| Exact assertions (`==`) | Fuzzy assertions (`>=`) |
| Fully deterministic | May be non-deterministic |
| Fast (< 1s) | Slower (seconds to minutes) |
| Purpose: verify correctness | Purpose: verify integration |

## Why Fuzzy Assertions?

Integration tests use lenient assertions (e.g., `>= 2` instead of `== 3`) because:

1. **External services may be unavailable**: APIs can be down, rate-limited, or slow
2. **Testing integration, not correctness**: We verify components communicate properly, not that external APIs return specific data
3. **Real-world conditions**: Results vary due to network issues, data updates, timeouts

**Example:**
```python
# Good: Verifies integration works even if one backend fails
assert result.legitimate_count >= 2, "Should find at least 2 out of 3"

# Bad: Fails if any external service is temporarily down
# assert result.legitimate_count == 3
```

## Interpreting Test Failures

**Integration tests may fail occasionally due to external factors.** This is expected and normal.

Common scenarios:

- **"Should find at least X entries"** → Backend API temporarily unavailable or rate-limiting
- **"Processing should take < Xs"** → Network latency or slow API response
- **Unexpected assessment result** → May indicate real bug; investigate backend responses

**Debugging steps:**
1. Re-run test to check if failure is intermittent
2. Check external service status (DOAJ, Crossref, etc.)
3. Run with verbose logging: `pytest -v -s --log-cli-level=DEBUG`
4. Review `aletheia-probe-detail.log` for backend responses

## Writing Integration Tests

**DO:**
- Use fuzzy assertions for external API results
- Mark tests: `@pytest.mark.integration`, `@pytest.mark.slow`, `@pytest.mark.requires_network`
- Document why assertions are lenient (comments)
- Test component interactions and error handling

**DON'T:**
- Use exact assertions for external API result counts
- Assume all backends are always available
- Test backend correctness (test integration instead)
- Create tests that fail intermittently without reason

**Example pattern:**
```python
@pytest.mark.integration
async def test_component_integration(self) -> None:
    """Test that normalizer output flows correctly to dispatcher.

    Verifies component integration, not individual backend correctness.
    """
    result = await assessor.assess(input_data)

    # Fuzzy assertions for external API results
    assert result.legitimate_count >= 1  # Not ==, allows service failures
    assert result.processing_time < 120
```

## Summary

Integration tests verify **component integration and data flow**, not API correctness. Fuzzy assertions account for external service variability. Occasional failures due to external factors are expected and normal.
