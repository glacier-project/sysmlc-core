______________________________________________________________________

## applyTo: '\*\*'

# General Instructions

## Python Coding Guidelines

Follow the [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html) as the primary reference for
Python code style. The sections below highlight key points and project-specific customizations.

### Comments

- Comments should never be on the right-hand side of code. They should always be on their own line above the code they
  refer to.

### General Style

- Adhere to PEP 8, the official style guide for Python code. Use a linter (e.g., Ruff, Flake8) to enforce this.
- Keep lines under 79 characters for maximum readability.

### Naming Conventions

- Use `snake_case` for function and variable names.
- Use `PascalCase` for class names.
- Use `UPPER_SNAKE_CASE` for constants.
- Avoid single-letter variable names unless they are loop counters or widely understood (e.g., `x`, `y` for
  coordinates).

### Docstrings

- All modules, functions, classes, and methods should have docstrings.

- Use triple double quotes `"""Docstring content"""`.

- After the opening triple quotes, the first line should be a short summary of the object's purpose and should be placed
  on the next line.

- The order is:

  - Summary line.
  - Blank line.
  - More detailed description (if necessary).
  - Blank line.
  - Any parameters and return value descriptions (if applicable) (`Params:`).
  - Blank line.
  - Return value description (if applicable) (`Returns:`).
  - Blank line.
  - Any exceptions raised (if applicable) (`Raises:`).

- Use imperative mood in the comments.

- Follow reStructuredText or Google style for formatting docstrings.

- The arguments name, type and description should be formatted as follows:

  ```python
  Args/Returns/Raises:
      <variable_name> (<variable_type>):
          <variable_description>
  ```

### Imports

- Imports should always be at the top of the file, after any module docstrings and `__future__` imports.
- Imports should be grouped in the following order:
  1. Standard library imports.
  1. Third-party imports.
  1. Local application/library specific imports.
- Each group should be separated by a blank line.
- Use absolute imports over relative imports.

### Functions and Methods

- Functions and methods should ideally be short and perform a single, well-defined task.
- Avoid excessive parameters; consider passing an object or dictionary if there are many related parameters.

### Error Handling

- Use `try-except` blocks for handling expected errors gracefully.
- Avoid broad `except` clauses (e.g., `except Exception:`). Be specific about the exceptions you catch.
- Do not suppress errors silently. Log them or re-raise them if appropriate.

### Type Hinting

- Use type hints for function arguments and return values to improve code readability and maintainability.
- Use type hints for variables where clarity is needed.

## GIT Repository Management

### Commits

Use the Conventional Commits format: `<type>(scope): short summary`

Examples:

- `feature(config): support dynamic environment loading`
- `fix(core): handle missing config file gracefully`
- `test(utils): add unit tests for retry logic`

Allowed types (use these as `<type>` in your commit messages):

- `feature` – New features
- `fix` – Bug fixes
- `documentation` – Documentation changes only
- `style` – Code style, formatting, missing semi-colons, etc. (no code meaning changes)
- `refactor` – Code changes that neither fix a bug nor add a feature
- `performance` – Code changes that improve performance
- `test` – Adding or correcting tests
- `build` – Changes to build system or external dependencies
- `ci` – Changes to CI configuration files and scripts
- `chore` – Maintenance tasks (e.g., updating dependencies, minor tooling)
- `revert` – Reverting previous commits
- `security` – Security-related improvements or fixes
- `ux` – User experience or UI improvements

Other Notes:

- Prefer simple, linear Git history. Use rebase over merge where possible.
- Use `pre-commit` hooks to enforce formatting, linting, and checks before commits.
- If unsure about a change, open a draft PR with a summary and rationale.

### Release Guidelines

We use one permanent branch, `main`, with short-lived pull request branches.

#### Branches

- `main`: The shared integration branch. Merge reviewed pull requests with passing CI; never push directly to it.
- `feature/<feature-name>`, `fix/<name>`, and `auto-update/<name>`: Temporary branches created from `main` and proposed back to `main` through pull requests.
- Version tags identify releases. A separate release branch is only needed when maintaining an older release line.

Here is the release process:

1. Create a release preparation branch from `main`.
1. Update `CHANGELOG.md` and the version in `pyproject.toml` through a pull request.
1. Run the repository's full validation suite and review the release changes before merging the pull request into `main`.
1. Tag the reviewed release commit on `main`: `git tag -a v<version-number> -m "Release v<version-number>"`.
1. Publish the approved release tag without pushing commits directly to `main`.
