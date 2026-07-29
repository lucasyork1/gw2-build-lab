from importlib.resources import files
from pathlib import Path


ROOT = Path(__file__).parents[1]
RUNTIME_SCHEMAS = (
    "manifest.schema.json",
    "dataset.schema.json",
    "entity.schema.json",
    "override.schema.json",
    "release-manifest.schema.json",
    "build.schema.json",
    "build-audit.schema.json",
    "analysis-rules.schema.json",
    "build-analysis.schema.json",
)


def test_packaged_schemas_match_public_contracts():
    packaged = files("gw2_wvw_data").joinpath("schemas")

    for name in RUNTIME_SCHEMAS:
        assert packaged.joinpath(name).read_bytes() == (
            ROOT / "schemas" / name
        ).read_bytes()
