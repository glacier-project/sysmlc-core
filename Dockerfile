FROM python:3.14.1-alpine3.21

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=UTF-8
ENV PYTHONPATH="${PYTHONPATH}:/app"

RUN apk add --update --no-cache gcc musl-dev
RUN pip install --no-cache-dir uv

COPY README.md pyproject.toml uv.lock ./
COPY sysml2frost/ sysml2frost
COPY examples/ examples

RUN uv sync --locked --no-dev
RUN python -m compileall -o 2 -f -j 0 /app/sysml2frost/

CMD ["uv", "run", "python", "-m", "sysml2frost"]
