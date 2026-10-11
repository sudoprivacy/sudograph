"""Hand edits cannot survive full regeneration, even with an unchanged bundle."""

from pathlib import Path

import pytest
import yaml

from compiler import app, spec
from tools import check_generated


@pytest.fixture
def model(tmp_path):
    config = tmp_path / "unrelated.yaml"
    config.write_text(yaml.safe_dump({"ontology": "Unrelated", "types": {}}), encoding="utf8")
    return app.bundle(spec.load(str(config)))


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("marks:'page'", "marks:'host'"),
        ("pointer-events:none", "pointer-events:auto"),
        ("#11141a", "#abcdef"),
        ("</body>", "<script>window.handEdited=true;</script></body>"),
    ],
)
def test_renderer_css_sdk_and_extra_script_edits_fail_with_unchanged_model(
    model, tmp_path, before, after
):
    output = tmp_path / "deliverable.html"
    native = app.render(model, language="en")
    assert before in native
    output.write_bytes(native.replace(before, after, 1).encode("utf8"))
    with pytest.raises(ValueError, match="shared compiler/renderer"):
        app.check_export(output, model, language="en")


def test_native_and_packed_exports_allow_only_platform_newline_conversion(model, tmp_path):
    output = tmp_path / "deliverable.html"
    for packed in [False, True]:
        rendered = app.render(model, language="en", packed=packed)
        for newline in ["\n", "\r\n"]:
            output.write_bytes(rendered.replace("\n", newline).encode("utf8"))
            app.check_export(output, model, language="en")
        output.write_bytes((rendered + "<script>window.injected=true;</script>").encode("utf8"))
        with pytest.raises(ValueError, match="shared compiler/renderer"):
            app.check_export(output, model, language="en")


def test_unregistered_or_renamed_html_cannot_silently_escape_the_ci_inventory(tmp_path):
    with pytest.raises(ValueError, match="empty checks"):
        check_generated.check_tree(tmp_path)
    (tmp_path / "renamed.html").write_text("<html>unowned</html>", encoding="utf8")
    with pytest.raises(ValueError, match="unregistered HTML"):
        check_generated.check_tree(tmp_path)


def test_all_checked_repository_deliverables_have_a_generation_owner():
    assert check_generated.check_tree(Path(app._ROOT) / "examples") == {
        "artifacts": 5, "checked": 5,
    }
