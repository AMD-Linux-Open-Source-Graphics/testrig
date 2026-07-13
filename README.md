# testrig

This is a tool that was written to make running the component tests for ROCm InBox packages easier and more consistent in both running and extracting error information.


## Usage

Testrig has two basic commands: run and check

  * `check` will look for packages declared as required and attempt to install any missing packages
  * `run` runs the tests after running the same process as `check`

## Global Settings

Testrig reads optional global settings from `/etc/testrig/settings.toml` and `~/.config/testrig/settings.toml`.

`ROCR_VISIBLE_DEVICES` can be set to a GPU UUID (or list accepted by ROCr, see [GPU Isolation Techniques](https://rocm.docs.amd.com/en/latest/conceptual/gpu-isolation.html#rocr-visible-devices)) to control GPU visibility during test binary execution.
By default this setting is empty. When empty, testrig takes no additional action.

## Code Formatting

All python code is formatted with [ruff](https://docs.astral.sh/ruff/formatter/)

## AI Code Policy

All contributors are responsible for code that is submitted in their name. Contributions assisted by AI tools is allowed
but such changes must have an `Assisted-by:` tag in the commit message following [the format declared by the Linux kernel](https://docs.kernel.org/process/coding-assistants.html#attribution)

`Assisted-by: AGENT_NAME:MODEL_VERSION [TOOL1] [TOOL2]`

Where:

  * `AGENT_NAME` is the name of the AI tool or framework
  * `MODEL_VERSION` is the specific model version used
  * `[TOOL1] [TOOL2]` are optional specialized analysis tools used (e.g., coccinelle, sparse, smatch, clang-tidy)

Basic development tools (git, gcc, make, editors) should not be listed.

Example:

`Assisted-by: Claude:claude-3-opus coccinelle sparse`


## Input Format

Testrig uses [TOML](https://toml.io/en/) for declaring rig information. The exact format should be considered unstable and likely to change between releases.

Each rig has a top-level `name` and one section per supported distro (for example `[ubuntu]` or `[fedora]`). A distro section declares:

  * `test_binary_path` - the directory containing the test entry points
  * `test_binaries` - an allowlist of entry point names to run. Each name is combined with `test_binary_path` to build an absolute path to the binary. Only the binaries listed here are executed.
  * `test_package_name` - the package that must be installed to run the tests
  * `test_debug_package_names` - packages providing debug symbols, used when gathering debug information on failures

Example:

```toml
name = "my-rig"

[ubuntu]
test_binary_path = "/opt/rocm/bin"
test_binaries = ["test_foo", "test_bar"]
test_package_name = "rocm-tests"
test_debug_package_names = ["rocm-tests-dbgsym"]
```

With the above, testrig runs `/opt/rocm/bin/test_foo` and `/opt/rocm/bin/test_bar`.


## Run Tests

Platform-specific tests like the ones for apt will only run on those systems. To exclude a set of tests from collection,
run:

`pytest tests/ --ignore tests/test_packagemanager_apt.py`
