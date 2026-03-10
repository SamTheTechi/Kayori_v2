name: Bug Report
description: File a bug report
labels: ["bug"]
body:
  - type: markdown
    attributes:
      value: |
        Thanks for taking the time to fill out this bug report!

  - type: textarea
    id: description
    attributes:
      label: Describe the bug
      description: A clear and concise description of what the bug is.
    validations:
      required: true

  - type: textarea
    id: reproduction
    attributes:
      label: To Reproduce
      description: Steps to reproduce the behavior.
      placeholder: |
        1. Configure adapter '...'
        2. Send message '...'
        3. See error
    validations:
      required: true

  - type: textarea
    id: expected
    attributes:
      label: Expected behavior
      description: A clear and concise description of what you expected to happen.
    validations:
      required: true

  - type: textarea
    id: actual
    attributes:
      label: Actual behavior
      description: What actually happened (include error messages, logs, etc.).
    validations:
      required: true

  - type: input
    id: python-version
    attributes:
      label: Python Version
      placeholder: "3.14"
    validations:
      required: true

  - type: input
    id: kayori-version
    attributes:
      label: Kayori Version
      placeholder: "0.1.0"
    validations:
      required: true

  - type: dropdown
    id: platform
    attributes:
      label: Platform
      description: Which platform adapter are you using?
      options:
        - Discord
        - Telegram
        - Console
        - Webhook
        - Multiple
        - Other
    validations:
      required: true

  - type: textarea
    id: context
    attributes:
      label: Additional context
      description: Add any other context about the problem here.
