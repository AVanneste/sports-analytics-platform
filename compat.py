"""Legacy unpickling compatibility bridge for PitchVision & CourtVision.

Ensures that pre-existing model bundles that were pickled when modules lived under
the generic 'src' namespace can still be unpickled cleanly without errors.
"""
import sys
import types
from pathlib import Path

# Ensure root paths are in sys.path
ROOT_DIR = Path(__file__).resolve().parent
FOOTBALL_DIR = ROOT_DIR / "Football"
TENNIS_DIR = ROOT_DIR / "Tennis"

for p in [ROOT_DIR, FOOTBALL_DIR, TENNIS_DIR]:
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

def setup_legacy_compat():
    """Register virtual 'src' modules to map legacy pickling namespaces."""
    try:
        import football_core.features.builder
        import football_core.features.elo
        import football_core.features.dixon_coles
        import football_core.features.form
        import football_core.features.h2h
        import football_core.features.referee
        
        import tennis_core.features.builder
        import tennis_core.features.elo
        import tennis_core.features.form
        import tennis_core.features.h2h
        import tennis_core.features.serve_return
    except Exception:
        # If modules are not yet loaded, return gracefully
        return

    # Virtual 'src' package
    src_mod = types.ModuleType("src")
    src_mod.__path__ = []

    # Virtual 'src.features' package
    features_mod = types.ModuleType("src.features")
    features_mod.__path__ = []

    # Virtual 'src.features.builder'
    builder_mod = types.ModuleType("src.features.builder")
    builder_mod.FootballFeaturePipeline = football_core.features.builder.FootballFeaturePipeline
    builder_mod.TennisFeaturePipeline = tennis_core.features.builder.TennisFeaturePipeline

    # Virtual 'src.features.elo'
    elo_mod = types.ModuleType("src.features.elo")
    elo_mod.FootballEloEngine = football_core.features.elo.FootballEloEngine
    elo_mod.TennisEloEngine = tennis_core.features.elo.TennisEloEngine

    # Virtual 'src.features.form'
    form_mod = types.ModuleType("src.features.form")
    form_mod.TeamFormTracker = football_core.features.form.TeamFormTracker
    form_mod.TennisFormEngine = tennis_core.features.form.TennisFormEngine

    # Virtual 'src.features.h2h'
    h2h_mod = types.ModuleType("src.features.h2h")
    h2h_mod.HeadToHeadTracker = football_core.features.h2h.HeadToHeadTracker
    h2h_mod.TennisH2HEngine = tennis_core.features.h2h.TennisH2HEngine

    # Virtual 'src.features.dixon_coles'
    dixon_mod = types.ModuleType("src.features.dixon_coles")
    dixon_mod.DixonColesEngine = football_core.features.dixon_coles.DixonColesEngine

    # Virtual 'src.features.referee'
    ref_mod = types.ModuleType("src.features.referee")
    ref_mod.RefereeStatsEngine = football_core.features.referee.RefereeStatsEngine

    # Virtual 'src.features.serve_return'
    sr_mod = types.ModuleType("src.features.serve_return")
    sr_mod.TennisServeReturnEngine = tennis_core.features.serve_return.TennisServeReturnEngine

    sys.modules["src"] = src_mod
    sys.modules["src.features"] = features_mod
    sys.modules["src.features.builder"] = builder_mod
    sys.modules["src.features.elo"] = elo_mod
    sys.modules["src.features.form"] = form_mod
    sys.modules["src.features.h2h"] = h2h_mod
    sys.modules["src.features.dixon_coles"] = dixon_mod
    sys.modules["src.features.referee"] = ref_mod
    sys.modules["src.features.serve_return"] = sr_mod

# Automatically run on import
setup_legacy_compat()

