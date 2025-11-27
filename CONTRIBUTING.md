# Contributing to SignalBridge Django SDK

Thank you for your interest in contributing to the SignalBridge Django SDK! This document provides guidelines for contributing to the project.

## Development Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/nugsoft/signalbridge-django.git
   cd signalbridge-django
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -e .
   ```

4. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your test credentials
   ```

## Code Standards

### Python Style
- Follow PEP 8 style guide
- Use type hints for all function parameters and return values
- Maximum line length: 100 characters
- Use docstrings for all public methods and classes

### Django Conventions
- Follow Django coding style
- Use Django's built-in features when possible
- Ensure compatibility with Django 3.2+

### Example Code Style
```python
def send_sms(
    self,
    recipient: str,
    message: str,
    sender_id: Optional[str] = None
) -> Dict:
    """
    Send an SMS message

    Args:
        recipient: Phone number in international format
        message: Message content
        sender_id: Optional custom sender ID

    Returns:
        Dict with success status and data
    """
    # Implementation
```

## Testing

### Running Tests
```bash
python -m pytest tests/
```

### Writing Tests
- Write tests for all new features
- Ensure test coverage is maintained
- Use Django's TestCase for integration tests
- Use unittest.mock for API mocking

Example test:
```python
from django.test import TestCase
from unittest.mock import patch
from signalbridge.client import SignalBridgeClient

class TestSMSSending(TestCase):
    @patch('signalbridge.client.requests.Session')
    def test_send_sms_success(self, mock_session):
        # Test implementation
        pass
```

## Pull Request Process

1. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**
   - Write clear, concise commit messages
   - Keep commits focused and atomic
   - Update documentation as needed

3. **Test your changes**
   ```bash
   python -m pytest tests/
   python manage.py test  # If using Django test project
   ```

4. **Update CHANGELOG.md**
   - Add your changes under `[Unreleased]` section
   - Follow the existing format

5. **Submit pull request**
   - Provide clear description of changes
   - Reference any related issues
   - Ensure CI checks pass

## Commit Message Format

Use conventional commit format:

```
type(scope): brief description

Detailed explanation if needed

Fixes #123
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting)
- `refactor`: Code refactoring
- `test`: Test additions or changes
- `chore`: Build process or auxiliary tool changes

## Reporting Issues

When reporting issues, please include:

1. **Django version** and **Python version**
2. **SDK version**
3. **Detailed description** of the issue
4. **Steps to reproduce**
5. **Expected vs actual behavior**
6. **Error messages and stack traces**
7. **Code samples** if applicable

## Feature Requests

We welcome feature requests! Please:

1. Check if the feature already exists
2. Clearly describe the use case
3. Explain why it would be useful
4. Provide examples if possible

## Code Review Process

- All submissions require review
- Maintainers will review PRs weekly
- Address feedback constructively
- Be patient - we're all volunteers

## Questions?

- Open an issue for public discussion
- Check existing issues and documentation first

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

Thank you for contributing to SignalBridge Django SDK! 🎉
