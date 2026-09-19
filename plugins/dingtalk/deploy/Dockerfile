FROM python:3.12-slim
WORKDIR /app
COPY dist/*.whl /tmp/wheels/
RUN pip install --no-cache-dir /tmp/wheels/*.whl && useradd --uid 10001 --create-home connector
USER 10001:10001
ENTRYPOINT ["opsmesh-dingtalk"]
