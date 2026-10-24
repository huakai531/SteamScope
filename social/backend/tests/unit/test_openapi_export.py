import json

from steamscope_social import export_openapi


def test_export_is_repeatable_utf8_with_lf_on_every_platform(tmp_path, monkeypatch):
    monkeypatch.setattr(export_openapi, "SOCIAL_ROOT", tmp_path)
    export_openapi.main()
    target = tmp_path / "docs" / "api" / "openapi.json"
    first = target.read_bytes()
    assert b"\r\n" not in first
    assert first.endswith(b"\n")
    assert json.loads(first)["openapi"].startswith("3.")
    export_openapi.main()
    assert target.read_bytes() == first
