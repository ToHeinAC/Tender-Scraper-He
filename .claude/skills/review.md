# Code Review Skill

Review the codebase for quality, security, and best practices.

## Instructions

When this skill is invoked, perform a comprehensive code review:

### 1. Run Automated Checks

Run the following tools to gather baseline quality metrics:

```bash
# Type checking
uv run mypy src/ --ignore-missing-imports 2>&1 | head -50

# Linting
uv run ruff check src/ 2>&1 | head -50

# Check for TODO/FIXME comments
grep -rn "TODO\|FIXME\|XXX\|HACK" src/ --include="*.py" | head -20
```

### 2. Review Code Quality

Check the following aspects:

- **Type Hints**: Are functions properly typed?
- **Error Handling**: Are exceptions handled appropriately?
- **Code Duplication**: Is there repeated code that should be refactored?
- **Function Length**: Are functions too long (>50 lines)?
- **Naming**: Are variables and functions named clearly?

### 3. Security Review

Look for common security issues:

- SQL injection vulnerabilities (string formatting in queries)
- Hardcoded secrets or API keys
- Unsafe file operations
- Missing input validation
- Exposed sensitive data in logs

### 4. Architecture Review

Verify the codebase follows project conventions:

- Repository pattern for database access
- Service layer for business logic
- Pydantic models for data validation
- Proper separation of concerns

### 5. Test Coverage

Check test coverage and quality:

```bash
# List test files
find tests/ -name "test_*.py" -type f

# Run tests with verbose output
uv run pytest tests/ -v --tb=short 2>&1 | tail -30
```

### 6. Documentation

Check for:

- Missing docstrings on public functions
- Outdated comments
- README accuracy

## Output Format

Provide a summary report with:

1. **Overall Health Score** (1-10)
2. **Critical Issues** (must fix)
3. **Warnings** (should fix)
4. **Suggestions** (nice to have)
5. **Positive Findings** (what's done well)

Focus on actionable feedback. For each issue, specify:
- File and line number
- Description of the issue
- Suggested fix
