import pytest


def test_missing_original_spec_requires_disclosed_readback(tmp_path,monkeypatch):
    import v6_report
    monkeypatch.setattr(v6_report,'ROOT',tmp_path)
    original=tmp_path/'fixture_original.md'
    with pytest.raises(RuntimeError,match='explicitly attributed readback'):
        v6_report.archive_spec(original)
    (tmp_path/'NEXT_STEPS_V6_READBACK.md').write_text('TEST FIXTURE: reconstructed text, not an original specification.')
    recovered=v6_report.archive_spec(original)
    assert recovered['origin']=='full_tool_readback_reconstruction'
    assert recovered['source_available'] is False
    assert recovered['byte_identity_to_original'] is None
    original.write_text('TEST FIXTURE: available original')
    copied=v6_report.archive_spec(original)
    assert copied['byte_identity_to_original'] is True
    assert (tmp_path/'NEXT_STEPS_V6.md').read_bytes()==original.read_bytes()
