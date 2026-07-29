"""Evidence-backed deterministic build analysis and comparison."""

from gw2_wvw_data.analysis.build import (
    AnalysisConclusion,
    BuildAnalysis,
    DimensionAnalysis,
    EvidenceReference,
    ImprovementApplicabilityReason,
    ImprovementAnalysis,
    analyze_build,
)
from gw2_wvw_data.analysis.compare import (
    BuildComparison,
    StructuralChange,
    StructuralReplacement,
    compare_builds,
)
from gw2_wvw_data.analysis.rules import (
    AnalysisRule,
    ComponentSelector,
    EvidenceSpec,
    ImprovementRule,
    RuleEffect,
    RuleSet,
    load_rules,
)

__all__ = [
    "AnalysisConclusion",
    "AnalysisRule",
    "BuildAnalysis",
    "BuildComparison",
    "ComponentSelector",
    "DimensionAnalysis",
    "EvidenceReference",
    "EvidenceSpec",
    "ImprovementApplicabilityReason",
    "ImprovementAnalysis",
    "ImprovementRule",
    "RuleEffect",
    "RuleSet",
    "StructuralChange",
    "StructuralReplacement",
    "analyze_build",
    "compare_builds",
    "load_rules",
]
