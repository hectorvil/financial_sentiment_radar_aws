"""Logging helpers for local and AWS execution."""

from __future__ import annotations

import logging
import os


def configure_logging() -> None:
    """Configure structured, concise logs.

    In ECS/Fargate, stdout/stderr are collected by CloudWatch Logs through the
    ``awslogs`` log driver defined in CloudFormation. The format avoids printing
    credentials or sensitive input values.
    """

    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)sZ %(name)s %(levelname)s action=%(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
