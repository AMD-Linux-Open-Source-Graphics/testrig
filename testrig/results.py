# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass, field

RESULTS_FILE_PLACEHOLDER = "{results_file}"
RESULTS_FILE_ENV_VAR = "TESTRIG_RESULTS_FILE"
MAX_MESSAGE_LENGTH = 1000


@dataclass
class CaseResult:
    name: str
    classname: str | None
    state: str  # PASS, FAIL or SKIP
    duration: float | None = None
    message: str | None = None


@dataclass
class ParsedResults:
    status: str  # ok, missing or invalid
    cases: list = field(default_factory=list)
    error: str | None = None

    def count(self, state):
        return sum(1 for case in self.cases if case.state == state)


def _parse_duration(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _detail_message(detail):
    message = detail.get("message") or (detail.text or "").strip()
    return message[:MAX_MESSAGE_LENGTH] or None


def _parse_testcase(element):
    state = "PASS"
    message = None
    for tag, tag_state in (("failure", "FAIL"), ("error", "FAIL"), ("skipped", "SKIP")):
        detail = element.find(tag)
        if detail is not None:
            state = tag_state
            message = _detail_message(detail)
            break
    else:
        # gtest and ctest also report outcomes through attributes
        status = (element.get("status") or "").lower()
        result = (element.get("result") or "").lower()
        if status == "fail":
            state = "FAIL"
        elif status in ("notrun", "disabled") or result in ("skipped", "suppressed"):
            state = "SKIP"

    return CaseResult(
        name=element.get("name", ""),
        classname=element.get("classname"),
        state=state,
        duration=_parse_duration(element.get("time")),
        message=message,
    )


def parse_junit(path):
    """Parse JUnit XML as written by pytest, gtest and ctest."""
    try:
        root = ElementTree.parse(path).getroot()
    except FileNotFoundError:
        return ParsedResults("missing", error=f"results file was not written: {path}")
    except (ElementTree.ParseError, OSError) as e:
        return ParsedResults("invalid", error=f"could not parse results file {path}: {e}")

    if root.tag not in ("testsuites", "testsuite"):
        return ParsedResults("invalid", error=f"unexpected root element <{root.tag}> in {path}")

    return ParsedResults("ok", [_parse_testcase(element) for element in root.iter("testcase")])


RESULT_PARSERS = {"junit": parse_junit}
RESULT_FORMATS = ("returncode", *RESULT_PARSERS)
