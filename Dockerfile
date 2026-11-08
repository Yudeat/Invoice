FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Copy installation inputs before sample assets so sample changes
# do not invalidate the package-installation layer.
COPY pyproject.toml README.md ./
COPY src ./src

RUN python -m pip install --no-cache-dir . \
    && python -m pip check

# Create a dedicated runtime user.
RUN groupadd --gid 10001 app \
    && useradd \
        --uid 10001 \
        --gid app \
        --create-home \
        --shell /usr/sbin/nologin \
        app

COPY samples ./samples

USER app

ENTRYPOINT ["invoice-extractor"]
CMD ["samples/rivertech_invoice.png", "--mock"]