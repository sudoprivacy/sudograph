# Installable compiler runtime

`sudograph-compiler` is a pure Python wheel containing the existing compiler,
shared renderer, translations, layout libraries and their notices. It is a
deployment dependency, not a model repository, source database or a second model
authority. Runtime dependencies remain pinned to `requirements.txt`.

An operator builds a wheel from a fixed source revision, runs the installed
acceptance gate and retains its SHA-256 receipt. The release workflow repeats
the complete repository verification before publishing a matching `v<version>`
tag's wheel and receipt. A host must pin the release asset and its hash; it must
not install a moving branch or fetch executable code from a model submission.
No release is claimed merely because this workflow exists.

```sh
pip install -r requirements.txt -r requirements-dev.txt
python -m hatchling build -t wheel -d dist
python -m tools.accept_installed_runtime --wheel dist/sudograph_compiler-0.1.0-py3-none-any.whl --receipt dist/installed-runtime.json
```

Install the verified wheel and its pinned Python dependencies into the worker's
dedicated environment. The existing worker entry points remain
`compiler.registration`, `compiler.workspace` and `compiler.review_host`. They
run from an empty private working directory; no source checkout is required.
The host still supplies the registered model path, current authenticated actor,
source provider and review resource through its trusted boundary. Installation
does not authorize a model, grant access to records or connect an agent.

The existing Sudowork adapter's `SUDOGRAPH_COMPILER_ROOT` currently names its
worker working directory. With this installed runtime it can point to an empty,
operator-owned directory. `SUDOGRAPH_PYTHON` must select the interpreter where
the verified wheel is installed. `SUDOGRAPH_MODEL_DIRECTORY` remains private
canonical model storage. A desktop-only SQLite path is never reinterpreted on a
cloud host; registration must target a source reachable by that worker.

The optional Nexus read bridge's JavaScript and lockfile are included, but its
Node dependency is not vendored into the wheel. A deployment using that adapter
must also provision its pinned Node package from the included lockfile and
perform Nexus authorization acceptance. Ordinary source registration, review
and context compilation do not require this optional bridge.

`tools.verify` builds the wheel twice, requires byte-for-byte reproducibility,
installs it without a network into a temporary target, and launches isolated
worker processes outside the repository. These processes use the invoking
Python's installed dependencies, not an independently resolved environment.
Runtime sources have fixed LF checkout endings and the implementation hash
orders logical paths identically on Windows and Linux. CI compares both
platforms' complete uncompressed package contents and implementation fingerprints.
ZIP platform headers and compression-library versions may change archive bytes;
each receipt separately records the exact wheel SHA-256 used for installation.
The gate checks source scanning, contract discovery, model edits/retries,
graph/context revisions, full native/packed HTML equality, resource/code hashes
and unchanged source bytes. A wheel cannot pass by importing the checkout.
This is installed-runtime acceptance; tenant grants, cloud deployment and the
authenticated Desktop/WebUI human journey remain separate acceptance.
