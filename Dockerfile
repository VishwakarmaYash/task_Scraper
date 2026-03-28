FROM python:3.11-slim

WORKDIR /app

# System deps for HTTP/XML work
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python deps the solution may use, plus test runner
RUN pip install --no-cache-dir \
    requests>=2.28.0 \
    beautifulsoup4>=4.12.0 \
    lxml>=4.9.0 \
    pytest>=7.0.0

# Copy task harness files
COPY task_tests.py  /app/task_tests.py
COPY parser.py      /app/parser.py
COPY run_script.sh  /app/run_script.sh
COPY instance_info.txt /app/instance_info.txt
COPY problem.md     /app/problem.md

RUN chmod +x /app/run_script.sh

WORKDIR /app

CMD ["./run_script.sh"]