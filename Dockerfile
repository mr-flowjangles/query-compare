FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN pip install --no-cache-dir .

# Mount your output directory here when you want to write a .sql file:
#   docker run --rm -i -v "$(pwd)/out:/work" query-compare ... -o /work/compare.sql
WORKDIR /work

ENTRYPOINT ["query-compare"]
