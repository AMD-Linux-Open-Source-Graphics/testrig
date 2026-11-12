# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

from testrig.results import MAX_MESSAGE_LENGTH, RESULT_FORMATS, parse_junit

PYTEST_JUNIT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites name="pytest tests">
  <testsuite name="pytest" errors="1" failures="1" skipped="1" tests="4" time="0.05">
    <testcase classname="test_x" name="test_pass" time="0.001" />
    <testcase classname="test_x" name="test_fail" time="0.002">
      <failure message="assert 1 == 2">traceback here</failure>
    </testcase>
    <testcase classname="test_x" name="test_skip" time="0.000">
      <skipped type="pytest.skip" message="not today">skip details</skipped>
    </testcase>
    <testcase classname="test_x" name="test_error" time="0.003">
      <error message="failed on setup">traceback here</error>
    </testcase>
  </testsuite>
</testsuites>
"""

GTEST_JUNIT = """<?xml version="1.0" encoding="UTF-8"?>
<testsuites tests="3" failures="1" disabled="1" errors="0" time="0.03" name="AllTests">
  <testsuite name="Foo" tests="3" failures="1" disabled="1" errors="0" time="0.03">
    <testcase name="Pass" status="run" result="completed" time="0.01" classname="Foo" />
    <testcase name="Fail" status="run" result="completed" time="0.02" classname="Foo">
      <failure message="foo.cc:10&#x0A;Expected equality" type=""><![CDATA[foo.cc:10]]></failure>
    </testcase>
    <testcase name="DISABLED_Off" status="notrun" result="suppressed" time="0" classname="Foo" />
  </testsuite>
</testsuites>
"""

CTEST_JUNIT = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="host" tests="4" failures="2" disabled="0" skipped="1" hostname="" time="1">
  <testcase name="ok_test" classname="ok_test" time="0.1" status="run"/>
  <testcase name="bad_test" classname="bad_test" time="0.2" status="fail">
    <failure message="Failed"/>
  </testcase>
  <testcase name="bad_attr_only" classname="bad_attr_only" time="0.2" status="fail"/>
  <testcase name="skip_test" classname="skip_test" time="0" status="notrun">
    <skipped message="Disabled"/>
  </testcase>
</testsuite>
"""


def write(tmp_path, content):
    path = tmp_path / "results.xml"
    path.write_text(content)
    return str(path)


def states(results):
    return {case.name: case.state for case in results.cases}


class TestParseJunit:
    def test_pytest(self, tmp_path):
        results = parse_junit(write(tmp_path, PYTEST_JUNIT))

        assert results.status == "ok"
        assert results.error is None
        assert states(results) == {
            "test_pass": "PASS",
            "test_fail": "FAIL",
            "test_skip": "SKIP",
            "test_error": "FAIL",
        }
        fail = results.cases[1]
        assert fail.classname == "test_x"
        assert fail.duration == 0.002
        assert fail.message == "assert 1 == 2"

    def test_gtest(self, tmp_path):
        results = parse_junit(write(tmp_path, GTEST_JUNIT))

        assert states(results) == {"Pass": "PASS", "Fail": "FAIL", "DISABLED_Off": "SKIP"}
        assert results.cases[1].message == "foo.cc:10\nExpected equality"

    def test_ctest(self, tmp_path):
        results = parse_junit(write(tmp_path, CTEST_JUNIT))

        assert states(results) == {
            "ok_test": "PASS",
            "bad_test": "FAIL",
            "bad_attr_only": "FAIL",
            "skip_test": "SKIP",
        }

    def test_count(self, tmp_path):
        results = parse_junit(write(tmp_path, PYTEST_JUNIT))

        assert results.count("PASS") == 1
        assert results.count("FAIL") == 2
        assert results.count("SKIP") == 1

    def test_message_falls_back_to_text_and_is_truncated(self, tmp_path):
        long_text = "x" * (MAX_MESSAGE_LENGTH + 50)
        content = f'<testsuite><testcase name="t"><failure>{long_text}</failure></testcase></testsuite>'

        results = parse_junit(write(tmp_path, content))

        assert results.cases[0].message == "x" * MAX_MESSAGE_LENGTH

    def test_missing_time_is_none(self, tmp_path):
        results = parse_junit(write(tmp_path, '<testsuite><testcase name="t"/></testsuite>'))

        assert results.cases[0].duration is None
        assert results.cases[0].classname is None

    def test_missing_file(self, tmp_path):
        results = parse_junit(str(tmp_path / "nope.xml"))

        assert results.status == "missing"
        assert results.cases == []
        assert "nope.xml" in results.error

    def test_truncated_file_is_invalid(self, tmp_path):
        results = parse_junit(write(tmp_path, PYTEST_JUNIT[:200]))

        assert results.status == "invalid"
        assert results.error

    def test_empty_file_is_invalid(self, tmp_path):
        assert parse_junit(write(tmp_path, "")).status == "invalid"

    def test_unexpected_root_is_invalid(self, tmp_path):
        results = parse_junit(write(tmp_path, "<html><testcase name='t'/></html>"))

        assert results.status == "invalid"
        assert "<html>" in results.error


def test_result_formats():
    assert RESULT_FORMATS == ("returncode", "junit")
