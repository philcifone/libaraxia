"""Per-request timing for development (ROADMAP 16.0g step 1,
docs/BACKEND-POLISH-SPEC.md section 1.1).

With PROFILE_REQUESTS=1 in .env, every request logs one line,

    PROFILE GET /base/index 200 84.2 ms 23 sql

and answers with a Server-Timing header (the browser's network panel shows
it), so slow pages and pages that run a query per row stand out. Off by
default; never turn it on in production (it logs every path).

The statement count comes from sqlite3's trace callback on the request's
connection (utils.database.get_db), which sees every statement run.
"""
import logging
import os
import time

from flask import g, request

logger = logging.getLogger('libaraxia.profile')


def enabled():
    return os.getenv('PROFILE_REQUESTS') == '1'


def count_statement(_sql):
    """sqlite3 trace callback: one more statement this request."""
    g.sql_count = g.get('sql_count', 0) + 1


def init_app(app):
    if not enabled():
        return

    @app.before_request
    def _start():
        g.profile_start = time.perf_counter()

    @app.after_request
    def _report(response):
        start = g.get('profile_start')
        if start is None:
            return response
        ms = (time.perf_counter() - start) * 1000
        count = g.get('sql_count', 0)
        response.headers['Server-Timing'] = f'app;dur={ms:.1f}, sql;desc="{count} statements"'
        if not request.path.startswith('/static/'):
            logger.info('PROFILE %s %s %s %.1f ms %d sql', request.method, request.full_path.rstrip('?'),
                        response.status_code, ms, count)
        return response
