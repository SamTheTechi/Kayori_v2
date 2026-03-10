# Contributing to Kayori v2

Thank you for considering contributing to Kayori v2! This document provides guidelines and instructions for contributing.

## Code of Conduct

Please read and follow our [Code of Conduct](CODE_OF_CONDUCT.md) to keep our community welcoming and inclusive.

## How to Contribute

### Reporting Bugs

1. Check if the bug has already been reported in [Issues](https://github.com/yourusername/kayori_v2/issues)
2. If not, create a new issue with:
   - A clear, descriptive title
   - Steps to reproduce the issue
   - Expected vs actual behavior
   - Environment details (Python version, OS, etc.)
   - Any relevant logs or error messages

### Suggesting Features

1. Check if the feature has already been suggested
2. Create a new issue with:
   - A clear description of the proposed feature
   - Why it would be useful
   - Any examples of how it would work

### Pull Requests

1. Fork the repository
2. Create a new branch from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. Make your changes
4. Run the smoke check and linting:
   ```bash
   uv run python tests/smoke_imports.py
   ruff check .
   ```
5. Commit your changes with clear, descriptive commit messages
6. Push to your fork and open a pull request

## Development Setup

1. Clone your fork:
   ```bash
   git clone https://github.com/yourusername/kayori_v2.git
   cd kayori_v2
   ```

2. Install dependencies:
   ```bash
   uv sync
   ```

3. Install pre-commit hooks:
   ```bash
   pre-commit install
   ```

4. Run the import smoke check:
   ```bash
   uv run python tests/smoke_imports.py
   ```

## Code Style

- We use `ruff` for linting and formatting
- Type hints are required for all public functions
- Follow PEP 8 style guidelines

## Verification

- Keep imports resolving cleanly with `tests/smoke_imports.py`
- Run `ruff check .` before opening a pull request

## Questions?

Feel free to open an issue for any questions or discussions.
