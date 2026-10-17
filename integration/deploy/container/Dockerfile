# PROPOSED ONLY: not built, not pushed, not deployed (decision D7). No secret in this file.
FROM python:3.12-slim
RUN useradd --create-home --uid 10001 epinoic
WORKDIR /srv/epinoic
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir ".[service,providers]"
COPY integration/deploy/container/entrypoint.sh /usr/local/bin/epinoic-entrypoint
USER epinoic
ENV EPINOIC_PROFILE=integration
EXPOSE 8080
ENTRYPOINT ["/bin/sh", "/usr/local/bin/epinoic-entrypoint"]
