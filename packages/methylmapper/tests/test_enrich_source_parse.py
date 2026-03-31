from methyl_mapper.bedtools_mapper import BedtoolsMapper


def test_parse_enrich_source_opentargets_token() -> None:
    use_grok, use_open_targets, use_disgenet = BedtoolsMapper._parse_enrich_source("opentargets")
    assert use_grok is False
    assert use_open_targets is True
    assert use_disgenet is False


def test_parse_enrich_source_combined_sources() -> None:
    use_grok, use_open_targets, use_disgenet = BedtoolsMapper._parse_enrich_source("grok+opentargets")
    assert use_grok is True
    assert use_open_targets is True
    assert use_disgenet is False
