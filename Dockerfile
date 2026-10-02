FROM python:3.13-slim

WORKDIR /srv
COPY pyproject.toml README.md LICENSE THIRD-PARTY-NOTICES.md ./
COPY src/ src/
RUN pip install --no-cache-dir .

EXPOSE 3012
USER 1000:1000
# 0.0.0.0 inside the container; publish the port only where the sign-in
# proxy can reach it, and set KHS_TRUSTED_PROXIES to the proxy's address:
# without it the server does not start.
CMD ["kobo-hardcover-sync", "serve", "--host", "0.0.0.0", "--port", "3012"]
