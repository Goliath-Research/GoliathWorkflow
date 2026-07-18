from types import SimpleNamespace

from methyl_validation.model_mc_runner import _exclude_configured_holdout


def test_model_mc_excludes_locked_holdout_from_reuse_pool() -> None:
    config = SimpleNamespace(
        holdout_exclude_from_training=True,
        holdout_partition="locked_test",
        validation_partitions=SimpleNamespace(
            locked_test=["/work/samples/control-held", "/work/samples/disease-held"]
        ),
    )

    filtered = _exclude_configured_holdout(
        [
            ("control", ["/work/samples/control-dev", "/other/control-held"]),
            ("disease", ["/work/samples/disease-dev", "/other/disease-held"]),
        ],
        config,
    )

    assert filtered == [
        ("control", ["/work/samples/control-dev"]),
        ("disease", ["/work/samples/disease-dev"]),
    ]


def test_model_mc_keeps_full_pool_when_holdout_exclusion_disabled() -> None:
    pools = [("control", ["/work/samples/control", "/work/samples/held"])]
    config = SimpleNamespace(
        holdout_exclude_from_training=False,
        holdout_partition="locked_test",
        validation_partitions=SimpleNamespace(locked_test=["/work/samples/held"]),
    )

    assert _exclude_configured_holdout(pools, config) == pools
