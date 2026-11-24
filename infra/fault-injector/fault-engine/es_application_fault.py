"""Helpers for simulating application-level Elasticsearch faults.
This module provides two small utility functions that you can call from your
services when you want to intentionally change the timeout or index name for a
request. The goal is to keep your normal behaviour correct, and only inject
faults when you explicitly enable them.
"""

from __future__ import annotations

import json
import time
from typing import Optional
from urllib import request as _urlrequest


def getCurrentFaultStatus(fault_name: str, api_url: str) -> bool:
    """Return the current flag status for ``fault_name`` from the fault API.
    This function performs an HTTP GET to ``api_url`` (for example,
    ``"http://localhost:8010/app-fault"``), expects a JSON array of objects
    with at least ``fault_name`` and ``flag`` fields, and returns the boolean
    flag for the matching ``fault_name``. If the fault name is not found or
    any error occurs, ``False`` is returned.
    """

    try:
        url = api_url.rstrip("/")
        req = _urlrequest.Request(url, headers={"accept": "application/json"})
        with _urlrequest.urlopen(req, timeout=5.0) as resp:  # type: ignore[arg-type]
            raw = resp.read()

        data = json.loads(raw.decode("utf-8"))
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("fault_name") == fault_name:
                    return bool(item.get("flag", False))
    except Exception:
        # On any network / JSON error, default to False as requested.
        return False

    # Fault name not found in response
    return False


def update_fault(fault_flag: bool, api_url: str, fault_name: str) -> bool:
    """Update the fault flag via the fault API and verify the new value.
    Parameters
    ----------
    fault_flag:
        Desired boolean flag value. ``True`` will call the ``.../set``
        endpoint and ``False`` will call the ``.../reset`` endpoint.
    api_url:
        Base URL of the fault API, for example ``"http://localhost:8010/app-fault"``.
    fault_name:
        Name of the fault, for example ``"ES_APPLICATION_TIMEOUT"``.
    Behaviour
    ---------
    1. Calls ``PUT {api_url}/{fault_name}/set`` when ``fault_flag`` is True,
       or ``PUT {api_url}/{fault_name}/reset`` when False.
    2. Then calls :func:`getCurrentFaultStatus` with the same ``fault_name`` and
       ``api_url``.
    3. Returns True if the current status matches ``fault_flag``, otherwise
       returns False. Any error during the update call results in False.
    """

    try:
        action = "set" if fault_flag else "reset"
        base = api_url.rstrip("/")
        url = f"{base}/{fault_name}/{action}"

        req = _urlrequest.Request(
            url,
            method="PUT",
            headers={"accept": "application/json"},
        )
        # Perform the update request; body is ignored because we verify via GET.
        with _urlrequest.urlopen(req, timeout=5.0):  # type: ignore[arg-type]
            pass
    except Exception:
        # If the update call itself fails, report failure.
        return False

    current_status = getCurrentFaultStatus(fault_name, api_url)
    return bool(current_status) == bool(fault_flag)


def sleep_for_seconds(seconds: int = 30) -> None:
    """Simple helper used by chaos experiments to pause execution.
    This is intentionally tiny so that the chaos framework can call a function
    that accepts keyword arguments (unlike :func:`time.sleep`, which only
    accepts a positional argument).
    """

    time.sleep(float(seconds))