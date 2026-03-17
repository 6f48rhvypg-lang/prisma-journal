# Contributing to PrismA - Secure Journal App

Thank you for your interest in contributing! This document provides guidelines for contributing to the project.

## Getting Started

1. **Fork the repository** and clone it locally
2. **Set up the development environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   venv\Scripts\activate     # Windows
   pip install -r requirements.txt
   ```
3. **Run the app locally:**
   ```bash
   python app/app.py
   ```

## Development Guidelines

### Code Style

- Follow PEP 8 for Python code
- Use meaningful variable and function names
- Add docstrings to functions and classes
- Keep functions focused and reasonably sized

### File Organization

- **Backend code** goes in `app/` directory
- **Database functions** in `app/database/db.py`
- **AI/ML utilities** in `app/utils/`
- **Templates** in `app/templates/`
- **Static files** (CSS, JS) in `app/static/`

### Commit Messages

- Use clear, descriptive commit messages
- Start with a verb: "Add", "Fix", "Update", "Remove"
- Reference issues if applicable: "Fix #123: ..."

### Testing

Before submitting:
1. Test your changes locally
2. Verify the app starts without errors
3. Test affected features manually
4. Check for console errors in the browser

## Submitting Changes

### Pull Requests

1. Create a feature branch: `git checkout -b feature/your-feature`
2. Make your changes
3. Test thoroughly
4. Push to your fork
5. Open a Pull Request with:
   - Clear description of changes
   - Screenshots for UI changes
   - Steps to test

### Bug Reports

When reporting bugs, include:
- Steps to reproduce
- Expected behavior
- Actual behavior
- Browser/OS information
- Console errors (if any)

### Feature Requests

For new features:
- Describe the use case
- Explain the proposed solution
- Consider privacy implications (local-first principle)

## Architecture Overview

See [ARCHITECTURE.md](../architecture/ARCHITECTURE.md) for details on:
- Project structure
- Database schema
- Service integrations
- Key design decisions

## Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Help others learn and grow

## Questions?

Open an issue for questions or discussions about contributions.
