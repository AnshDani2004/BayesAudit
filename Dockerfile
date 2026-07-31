FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md LICENSE CITATION.cff ./
COPY src ./src
COPY configs ./configs
COPY scenarios ./scenarios
COPY docs ./docs
COPY tests ./tests
RUN pip install --no-cache-dir -e ".[dev]"

CMD ["pytest"]

