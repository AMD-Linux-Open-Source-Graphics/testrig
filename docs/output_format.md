# testrig output format

To make tracking run history easier, testrig will enable creating a machine-readable summary file after completing execution.

## File Format

The summary will be in JSON for the following reasons

  1. While testrig uses TOML for configuration files, python only has TOML parsing in the stdlib and one of the design philosophies of testrig is to minimize external dependencies
  2. while not the best for human read-ability, JSON is well supported among languages and easily parsable by pretty much anything

## Output schema

The detailed schema is stored in [output_format.schema.json](output_format.schema.json)

All dates and times and time durations will adhere to the [ISO 8601 Format](https://en.wikipedia.org/wiki/ISO_8601). Timezones must be included in all timestamps and by default, timestamps should be in UTC.

The UUID will be formatted according to [RFC9562 UUID version 7](https://datatracker.ietf.org/doc/html/rfc9562.html#name-uuid-version-7)

For items that may not exist (e.g git information), the keys will still exist but have a value of null

all keys will be written in snake case (snake_case) and in all lower case

## Execution state

The state will be an enum with the following possible values:

 - PASS
   * no errors detected
 - WARN
   * some failures detected but didn't hit full failure heuristics
 - FAIL
   * failures detected and failure heuristics met
 - SYSTEM_FAIL
   * this is a failure that was due to the system under test
 - RUNNER_FAIL
   * this is a failure that was caused by an internal testrig failure
 - UNKNOWN
   * catch-all for anything that doesn't fit the other states

At the time of writing, the heuristics have not been implemented but are described here to make sure that they are taken into account for the summary output format

# testrig output contents

This list will likely change over time but the initial release will contain

 * schema version
 * testrig version
 * run uuid
 * start time
 * end time
 * total runtime
 * is dry_run (true/false)
 * Runner System information:
   - running kernel information
     + is inbox kernel (true/false)
     + version
   - list of all installed system packages with versions
     + name as key, version as value
   - distro family
   - distro
   - distro release
   - available memory
   - CPU
   - CPU arch
   - free memory at run start
   - user account doing run
   - user account groups
   - hostname
   - container type: one of `docker`, `podman`, `lxc`, or `none` (indicates
     which, if any, container system is running the process at execution
     time)
 * GPU Information
   - list of gpus including
     + ISA
     + marketing name
     + vendor name
     + firmware version
 * git information
    - git repo URI
    - git revision
    - is modified (true/false)
 * test information
   - list of individual results
     + binary
     + command
     + execution state
     + start time
     + end time
     + duration
     + return code
     + executed command
 * debug run information
   - was debug run
   - replicated list of binaries which debug was run for
 * testrig options used at runtime
 * overall result information
   - see state values and explanations above

## Example output

The following is a non-normative example illustrating the structure described
above. Field names and nesting are illustrative and will track the schema once
it is published.

```json
{
  "schema_version": "1.0.0",
  "testrig_version": "0.0.7",
  "run_uuid": "018f9a1c-7b3e-7c2a-9f4d-3a1b2c4d5e6f",
  "start_time": "2026-08-19T17:00:00+00:00",
  "end_time": "2026-08-19T17:04:12+00:00",
  "total_runtime": "PT4M12S",
  "is_dry_run": false,
  "runner_system_information": {
    "kernel": {
      "is_inbox_kernel": true,
      "version": "6.11.4-201.fc45.x86_64"
    },
    "installed_packages": {
      "rocm-tests": "6.2.0-1",
      "gdb": "14.2-1"
    },
    "distro_family": "fedora",
    "distro": "fedora",
    "distro_release": "45",
    "available_memory": "128 GiB",
    "cpu": "AMD EPYC 7443 24-Core Processor",
    "cpu_arch": "x86_64",
    "free_memory_at_run_start": "119 GiB",
    "user_account": "tflink",
    "user_account_groups": ["tflink", "wheel", "render", "video"],
    "hostname": "node-01",
    "container_type": "none"
  },
  "gpu_information": [
    {
      "isa": "amdgcn-amd-amdhsa--gfx90a",
      "marketing_name": "AMD Instinct MI210",
      "vendor_name": "AMD",
      "firmware_version": "0x00000000"
    }
  ],
  "git_information": {
    "repo_uri": "https://github.com/example/rocm-tests.git",
    "revision": "9f3c1a2b7d4e5f60718293a4b5c6d7e8f9012345",
    "is_modified": false
  },
  "test_information": [
    {
      "binary": "/usr/lib/rocm-tests/test_foo",
      "command": ["/usr/lib/rocm-tests/test_foo", "--gtest_filter=*Smoke*"],
      "execution_state": "PASS",
      "start_time": "2026-08-19T17:01:00+00:00",
      "end_time": "2026-08-19T17:01:30+00:00",
      "duration": "PT30S",
      "return_code": 0
    },
    {
      "binary": "/usr/lib/rocm-tests/test_bar",
      "command": ["/usr/lib/rocm-tests/test_bar", "--gtest_filter=*Smoke*"],
      "execution_state": "FAIL",
      "start_time": "2026-08-19T17:01:30+00:00",
      "end_time": "2026-08-19T17:03:45+00:00",
      "duration": "PT2M15S",
      "return_code": 1
    }
  ],
  "debug_run_information": {
    "was_debug_run": true,
    "binaries": ["/usr/lib/rocm-tests/test_bar"]
  },
  "testrig_options": {
    "disable_debug": false,
    "ROCR_VISIBLE_DEVICES": "",
    "gdb_pyfile_dir": "/usr/share/testrig",
    "enable_file_output": false
  },
  "overall_result": "FAIL"
}
```