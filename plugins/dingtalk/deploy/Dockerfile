FROM python:3.12-slim@sha256:2f17fc044b579bab302c2e8054d3a686e2cb9a83de48e70534b94cd8ebbe06a9
WORKDIR /app
COPY dist/*.whl /tmp/wheels/
COPY dist/runtime-requirements.txt /tmp/runtime-requirements.txt
RUN pip install --no-cache-dir --require-hashes -r /tmp/runtime-requirements.txt \
    && pip install --no-cache-dir --no-deps /tmp/wheels/*.whl \
    && pip check \
    && useradd --uid 10001 --create-home connector
USER 10001:10001
ENTRYPOINT ["opsmesh-dingtalk"]
