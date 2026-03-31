"""Tests for production project path remapping."""

from methyl_validation.path_remap import apply_path_remap_to_nested, remap_path_string


def test_remap_path_string_longest_prefix():
    m = {"/a": "/x", "/a/b": "/y"}
    assert remap_path_string("/a/b/c", m) == "/y/c"
    assert remap_path_string("/a/z", m) == "/x/z"


def test_apply_path_remap_to_nested_mutates():
    d = {
        "samples_base_path": "/old/root",
        "controls": {"groups": [{"sample_paths": ["/old/root/s1/x.csv"]}]},
    }
    apply_path_remap_to_nested(d, {"/old/root": "/new/root"})
    assert d["samples_base_path"] == "/new/root"
    assert d["controls"]["groups"][0]["sample_paths"] == ["/new/root/s1/x.csv"]
