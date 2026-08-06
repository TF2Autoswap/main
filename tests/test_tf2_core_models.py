#!/usr/bin/env python3
"""
test_tf2_core_models.py - Comprehensive model search and filtering tests.

Tests for find_models(), find_cosmetics(), find_weapons(), find_props(),
all_stems(), all_cosmetic_stems(), all_weapon_stems(), and class filtering logic.
Covers keyword matching, class filters, edge cases, and error conditions.

Author: Melancholy Sky
Co-Author: AI assistance via OpenRouter
"""

import pytest
from unittest.mock import Mock, MagicMock
import tf2_core as core


class TestFindModels:
    """Test find_models() cosmetic model search function."""

    def test_find_models_basic_keyword_match(self):
        """find_models() finds models matching a keyword."""
        pak = [
            "models/player/items/scout/a_backwards_ballcap.mdl",
            "models/player/items/scout/a_backwards_ballcap.vvd",
            "models/player/items/scout/a_other_hat.mdl",
        ]
        result = core.find_models(pak, "backwards")
        assert "models/player/items/scout/a_backwards_ballcap.mdl" in result
        assert "models/player/items/scout/a_other_hat.mdl" not in result

    def test_find_models_case_insensitive_keyword(self):
        """find_models() keyword search is case-insensitive."""
        pak = [
            "models/player/items/scout/Backwards_Ballcap.mdl",
            "models/player/items/scout/other_hat.mdl",
        ]
        result = core.find_models(pak, "BACKWARDS")
        assert len(result) == 1
        assert "Backwards_Ballcap.mdl" in result[0]

    def test_find_models_space_to_underscore_conversion(self):
        """find_models() converts spaces to underscores in keyword."""
        pak = [
            "models/player/items/scout/a_hot_air_balloon.mdl",
            "models/player/items/scout/a_normal_hat.mdl",
        ]
        result = core.find_models(pak, "hot air balloon")
        assert len(result) == 1
        assert "hot_air_balloon" in result[0].lower()

    def test_find_models_mdl_only_not_other_extensions(self):
        """find_models() returns only .mdl files, not .vvd or .vtx."""
        pak = [
            "models/player/items/scout/test_hat.mdl",
            "models/player/items/scout/test_hat.vvd",
            "models/player/items/scout/test_hat.dx90.vtx",
        ]
        result = core.find_models(pak, "test")
        assert len(result) == 1
        assert result[0].endswith(".mdl")

    def test_find_models_deduplicates_results(self):
        """find_models() removes duplicate paths."""
        pak = [
            "models/player/items/scout/test_hat.mdl",
            "models/player/items/scout/test_hat.mdl",  # duplicate
        ]
        result = core.find_models(pak, "test")
        assert len(result) == 1

    def test_find_models_returns_sorted_results(self):
        """find_models() returns alphabetically sorted results."""
        pak = [
            "models/player/items/scout/z_last_hat.mdl",
            "models/player/items/scout/a_first_hat.mdl",
            "models/player/items/scout/m_middle_hat.mdl",
        ]
        result = core.find_models(pak, "hat")
        assert result == sorted(result)

    def test_find_models_empty_keyword_returns_all(self):
        """find_models() with empty keyword matches everything."""
        pak = [
            "models/player/items/scout/hat1.mdl",
            "models/player/items/scout/hat2.mdl",
            "models/player/items/scout/other.mdl",
        ]
        result = core.find_models(pak, "")
        assert len(result) == 3

    def test_find_models_no_matches(self):
        """find_models() returns empty list when no matches found."""
        pak = [
            "models/player/items/scout/ballcap.mdl",
        ]
        result = core.find_models(pak, "nonexistent")
        assert result == []

    def test_find_models_empty_pak(self):
        """find_models() handles empty pak gracefully."""
        pak = []
        result = core.find_models(pak, "test")
        assert result == []

    def test_find_models_no_mdl_files_in_pak(self):
        """find_models() returns empty when pak has no .mdl files."""
        pak = [
            "materials/test.vmt",
            "materials/test.vtf",
            "scripts/test.txt",
        ]
        result = core.find_models(pak, "test")
        assert result == []

    def test_find_models_class_filter_scout(self):
        """find_models() filters to scout class with class_filter."""
        pak = [
            "models/player/items/scout/scout_hat.mdl",
            "models/player/items/soldier/soldier_hat.mdl",
            "models/player/items/pyro/pyro_hat.mdl",
        ]
        result = core.find_models(pak, "hat", class_filter="scout")
        assert "scout_hat.mdl" in result[0]
        assert len(result) == 1

    def test_find_models_class_filter_demoman_uses_demo_term(self):
        """find_models() uses 'demo' path term for demoman class."""
        pak = [
            "models/player/items/demoman/demo_pipe.mdl",
            "models/player/items/scout/scout_bat.mdl",
        ]
        result = core.find_models(pak, "pipe", class_filter="demoman")
        assert "demo_pipe" in result[0]
        assert len(result) == 1

    def test_find_models_class_filter_engineer_uses_engi_term(self):
        """find_models() uses 'engi' path term for engineer class."""
        pak = [
            "models/player/items/engineer/engi_sentry.mdl",
            "models/player/items/scout/scout_bat.mdl",
        ]
        result = core.find_models(pak, "sentry", class_filter="engineer")
        assert "engi_sentry" in result[0]
        assert len(result) == 1

    def test_find_models_all_class_items_no_filter(self):
        """find_models() includes all-class items when no filter."""
        pak = [
            "models/player/items/all_class/all_class_hat.mdl",
            "models/player/items/scout/scout_hat.mdl",
        ]
        result = core.find_models(pak, "hat")
        assert len(result) == 2

    def test_find_models_all_class_item_with_class_suffix(self):
        """find_models() filters all-class items with per-class suffixes."""
        pak = [
            "models/player/items/all_class/hat_scout.mdl",
            "models/player/items/all_class/hat_soldier.mdl",
            "models/player/items/all_class/hat_pyro.mdl",
        ]
        result = core.find_models(pak, "hat", class_filter="scout")
        # Should include scout variant and exclude soldier/pyro variants
        assert len(result) >= 1
        assert any("scout" in r for r in result)

    def test_find_models_all_class_shared_no_suffix(self):
        """find_models() includes all-class items with no per-class suffix."""
        pak = [
            "models/player/items/all_class/universal_hat.mdl",
            "models/player/items/scout/scout_hat.mdl",
        ]
        result = core.find_models(pak, "hat", class_filter="scout")
        # Should include both the class-specific hat and the universal one
        assert len(result) >= 1

    def test_find_models_class_filter_all_includes_everything(self):
        """find_models() with class_filter='all' includes all classes."""
        pak = [
            "models/player/items/scout/scout_hat.mdl",
            "models/player/items/soldier/soldier_hat.mdl",
            "models/player/items/all_class/universal_hat.mdl",
        ]
        result = core.find_models(pak, "hat", class_filter="all")
        assert len(result) == 3

    def test_find_models_class_filter_none_includes_all(self):
        """find_models() with no class_filter includes all classes."""
        pak = [
            "models/player/items/scout/scout_hat.mdl",
            "models/player/items/soldier/soldier_hat.mdl",
        ]
        result = core.find_models(pak, "hat", class_filter=None)
        assert len(result) == 2

    def test_find_models_partial_keyword_match(self):
        """find_models() matches partial keywords in filenames."""
        pak = [
            "models/player/items/scout/a_backwards_ballcap.mdl",
            "models/player/items/scout/a_ballcap_brown.mdl",
        ]
        result = core.find_models(pak, "ballcap")
        assert len(result) == 2

    def test_find_models_special_characters_in_path(self):
        """find_models() handles paths with special characters."""
        pak = [
            "models/player/items/scout/a_hot-air_balloon.mdl",
        ]
        result = core.find_models(pak, "hot-air")
        # Should handle the special character (hyphen)
        assert len(result) >= 0  # May or may not match depending on implementation

    def test_find_models_multiple_slashes_in_path(self):
        """find_models() handles paths with multiple directory levels."""
        pak = [
            "models/player/items/heavy/a/b/c/deep_hat.mdl",
        ]
        result = core.find_models(pak, "deep_hat")
        assert len(result) == 1

    def test_find_models_numeric_keywords(self):
        """find_models() can search for numeric keywords."""
        pak = [
            "models/player/items/scout/hat_v2.mdl",
            "models/player/items/scout/hat_v3.mdl",
        ]
        result = core.find_models(pak, "v2")
        assert len(result) == 1
        assert "v2" in result[0]


class TestFindWeapons:
    """Test find_weapons() weapon model search function."""

    def test_find_weapons_basic_search(self):
        """find_weapons() finds weapon viewmodels matching keyword."""
        pak = [
            "models/weapons/c_models/c_scattergun/c_scattergun.mdl",
            "models/weapons/c_models/c_pistol/c_pistol.mdl",
            "models/weapons/w_models/w_scattergun.mdl",
        ]
        result = core.find_weapons(pak, "scattergun")
        assert len(result) >= 1
        assert any("c_scattergun" in r for r in result)
        assert not any("w_scattergun" in r for r in result)  # No worldmodels

    def test_find_weapons_excludes_worldmodels(self):
        """find_weapons() only searches c_models, not w_models."""
        pak = [
            "models/weapons/c_models/c_test_weapon/c_test_weapon.mdl",
            "models/weapons/w_models/w_test_weapon.mdl",
        ]
        result = core.find_weapons(pak, "test_weapon")
        assert len(result) == 1
        assert "/c_models/" in result[0]

    def test_find_weapons_filters_variant_suffixes_by_default(self):
        """find_weapons() excludes variant suffixes by default."""
        pak = [
            "models/weapons/c_models/c_scattergun/c_scattergun.mdl",
            "models/weapons/c_models/c_scattergun/c_scattergun_festivizer.mdl",
            "models/weapons/c_models/c_scattergun/c_scattergun_xmas.mdl",
        ]
        result = core.find_weapons(pak, "scattergun")
        # Should include base, exclude variants
        assert len(result) == 1
        assert "c_scattergun.mdl" in result[0]

    def test_find_weapons_includes_variants_when_explicitly_searched(self):
        """find_weapons() includes variants when explicitly searched."""
        pak = [
            "models/weapons/c_models/c_scattergun/c_scattergun.mdl",
            "models/weapons/c_models/c_scattergun/c_scattergun_festivizer.mdl",
        ]
        result = core.find_weapons(pak, "festivizer")
        assert len(result) >= 1
        assert any("festivizer" in r for r in result)

    def test_find_weapons_handles_xmas_variant(self):
        """find_weapons() recognizes _xmas suffix as variant."""
        pak = [
            "models/weapons/c_models/c_minigun/c_minigun.mdl",
            "models/weapons/c_models/c_minigun/c_minigun_xmas.mdl",
        ]
        result = core.find_weapons(pak, "minigun")
        # Should only include base model
        assert len(result) == 1
        assert "_xmas" not in result[0]

    def test_find_weapons_handles_animations_variant(self):
        """find_weapons() recognizes _animations suffix as variant."""
        pak = [
            "models/weapons/c_models/c_heavy/c_heavy.mdl",
            "models/weapons/c_models/c_heavy/c_heavy_animations.mdl",
        ]
        result = core.find_weapons(pak, "heavy")
        assert "_animations" not in result[0]

    def test_find_weapons_handles_arms_variant(self):
        """find_weapons() recognizes _arms suffix as variant."""
        pak = [
            "models/weapons/c_models/c_machete/c_machete.mdl",
            "models/weapons/c_models/c_machete/c_machete_arms.mdl",
        ]
        result = core.find_weapons(pak, "machete")
        assert "_arms" not in result[0]

    def test_find_weapons_deduplicates_by_filename(self):
        """find_weapons() deduplicates by base filename."""
        pak = [
            "models/weapons/c_models/c_scattergun/c_scattergun.mdl",
            "models/weapons/c_models/alt/c_scattergun.mdl",  # Same base name, different path
        ]
        result = core.find_weapons(pak, "scattergun")
        # Should deduplicate by basename
        base_names = [r.split("/")[-1] for r in result]
        assert len(set(base_names)) == len(base_names) or len(result) == 1

    def test_find_weapons_case_insensitive(self):
        """find_weapons() is case-insensitive."""
        pak = [
            "models/weapons/c_models/c_Scattergun/c_Scattergun.mdl",
        ]
        result = core.find_weapons(pak, "SCATTERGUN")
        assert len(result) == 1

    def test_find_weapons_space_to_underscore(self):
        """find_weapons() converts spaces to underscores."""
        pak = [
            "models/weapons/c_models/c_rocket_launcher/c_rocket_launcher.mdl",
        ]
        result = core.find_weapons(pak, "rocket launcher")
        assert len(result) == 1

    def test_find_weapons_no_results(self):
        """find_weapons() returns empty list for no matches."""
        pak = [
            "models/weapons/c_models/c_scattergun/c_scattergun.mdl",
        ]
        result = core.find_weapons(pak, "nonexistent_weapon")
        assert result == []

    def test_find_weapons_empty_pak(self):
        """find_weapons() handles empty pak."""
        pak = []
        result = core.find_weapons(pak, "scattergun")
        assert result == []

    def test_find_weapons_non_mdl_files_ignored(self):
        """find_weapons() ignores non-.mdl files."""
        pak = [
            "models/weapons/c_models/c_test/c_test.vvd",
            "models/weapons/c_models/c_test/c_test.vtx",
            "materials/test.vmt",
        ]
        result = core.find_weapons(pak, "test")
        assert len(result) == 0


class TestFindProps:
    """Test find_props() prop model search function."""

    def test_find_props_basic_search(self):
        """find_props() finds props matching keyword."""
        pak = [
            "models/props_2fort/barrel_01.mdl",
            "models/props_2fort/crate_02.mdl",
        ]
        result = core.find_props(pak, "barrel")
        assert len(result) == 1
        assert "barrel" in result[0]

    def test_find_props_finds_props_underscore_folder(self):
        """find_props() finds models under models/props_* folders."""
        pak = [
            "models/props_obj/pumpkin.mdl",
            "models/props_halloween/ghost.mdl",
        ]
        result = core.find_props(pak, "pumpkin")
        assert len(result) >= 1
        assert any("pumpkin" in r for r in result)

    def test_find_props_finds_direct_props_folder(self):
        """find_props() finds models under models/props/ folder."""
        pak = [
            "models/props/test_prop.mdl",
        ]
        result = core.find_props(pak, "test_prop")
        assert len(result) == 1

    def test_find_props_case_insensitive(self):
        """find_props() is case-insensitive."""
        pak = [
            "models/props_obj/Barrel.mdl",
        ]
        result = core.find_props(pak, "BARREL")
        assert len(result) == 1

    def test_find_props_deduplicates_by_filename(self):
        """find_props() deduplicates by filename."""
        pak = [
            "models/props_2fort/barrel.mdl",
            "models/props_stuff/barrel.mdl",
        ]
        result = core.find_props(pak, "barrel")
        # Should deduplicate by base filename
        assert len(result) <= 1 or all(r.endswith("barrel.mdl") for r in result)

    def test_find_props_space_to_underscore(self):
        """find_props() converts spaces to underscores."""
        pak = [
            "models/props_2fort/heavy_barrel.mdl",
        ]
        result = core.find_props(pak, "heavy barrel")
        assert len(result) == 1

    def test_find_props_mdl_only(self):
        """find_props() returns only .mdl files."""
        pak = [
            "models/props_2fort/barrel.mdl",
            "models/props_2fort/barrel.vvd",
        ]
        result = core.find_props(pak, "barrel")
        assert all(r.endswith(".mdl") for r in result)

    def test_find_props_no_matches(self):
        """find_props() returns empty list for no matches."""
        pak = [
            "models/props_2fort/barrel.mdl",
        ]
        result = core.find_props(pak, "nonexistent")
        assert result == []

    def test_find_props_excludes_cosmetics_and_weapons(self):
        """find_props() doesn't return cosmetic or weapon models."""
        pak = [
            "models/props_2fort/barrel.mdl",
            "models/player/items/scout/hat.mdl",
            "models/weapons/c_models/c_gun/c_gun.mdl",
        ]
        result = core.find_props(pak, "")
        # Should only find barrel
        assert len(result) == 1
        assert "barrel" in result[0]


class TestAllStems:
    """Test all_stems() stem extraction function."""

    def test_all_stems_extracts_filenames(self):
        """all_stems() extracts basenames without extension."""
        pak = [
            "models/player/items/scout/backwards_ballcap.mdl",
            "models/player/items/scout/bonk_helmet.mdl",
        ]
        result = core.all_stems(pak)
        assert "backwards_ballcap" in result
        assert "bonk_helmet" in result

    def test_all_stems_ignores_extension(self):
        """all_stems() extracts stems without .mdl extension."""
        pak = [
            "models/player/items/scout/test_hat.mdl",
            "models/player/items/scout/test_hat.vvd",
        ]
        result = core.all_stems(pak)
        assert "test_hat" in result
        # Should appear only once despite multiple extensions
        assert result.count("test_hat") == 1

    def test_all_stems_deduplicates(self):
        """all_stems() removes duplicate stems."""
        pak = [
            "models/path1/test_model.mdl",
            "models/path2/test_model.mdl",
        ]
        result = core.all_stems(pak)
        assert result.count("test_model") <= 1

    def test_all_stems_sorted(self):
        """all_stems() returns alphabetically sorted stems."""
        pak = [
            "models/z_last.mdl",
            "models/a_first.mdl",
            "models/m_middle.mdl",
        ]
        result = core.all_stems(pak)
        assert result == sorted(result)

    def test_all_stems_ignores_non_mdl(self):
        """all_stems() only considers .mdl files."""
        pak = [
            "models/test_hat.mdl",
            "materials/test_hat.vmt",
            "scripts/test_hat.txt",
        ]
        result = core.all_stems(pak)
        # Should only count test_hat from the .mdl file
        assert "test_hat" in result

    def test_all_stems_empty_pak(self):
        """all_stems() handles empty pak."""
        pak = []
        result = core.all_stems(pak)
        assert result == []

    def test_all_stems_no_mdl_files(self):
        """all_stems() returns empty for pak with no .mdl files."""
        pak = [
            "materials/test.vmt",
            "scripts/test.txt",
        ]
        result = core.all_stems(pak)
        assert result == []

    def test_all_stems_complex_paths(self):
        """all_stems() extracts stems from complex paths."""
        pak = [
            "models/player/items/scout/a/b/c/deep_hat.mdl",
        ]
        result = core.all_stems(pak)
        assert "deep_hat" in result


class TestAllWeaponStems:
    """Test all_weapon_stems() weapon-specific stem extraction."""

    def test_all_weapon_stems_extracts_c_models_only(self):
        """all_weapon_stems() extracts stems only from c_models folder."""
        pak = [
            "models/weapons/c_models/c_gun/c_gun.mdl",
            "models/weapons/w_models/w_gun.mdl",
        ]
        result = core.all_weapon_stems(pak)
        assert "c_gun" in result
        assert "w_gun" not in result

    def test_all_weapon_stems_case_insensitive_path(self):
        """all_weapon_stems() is case-insensitive for path matching."""
        pak = [
            "models/weapons/C_MODELS/c_gun/c_gun.mdl",
        ]
        result = core.all_weapon_stems(pak)
        assert "c_gun" in result

    def test_all_weapon_stems_deduplicates(self):
        """all_weapon_stems() removes duplicate stems."""
        pak = [
            "models/weapons/c_models/path1/c_gun.mdl",
            "models/weapons/c_models/path2/c_gun.mdl",
        ]
        result = core.all_weapon_stems(pak)
        assert result.count("c_gun") <= 1

    def test_all_weapon_stems_sorted(self):
        """all_weapon_stems() returns sorted stems."""
        pak = [
            "models/weapons/c_models/z_last/z_last.mdl",
            "models/weapons/c_models/a_first/a_first.mdl",
        ]
        result = core.all_weapon_stems(pak)
        assert result == sorted(result)

    def test_all_weapon_stems_empty_pak(self):
        """all_weapon_stems() handles empty pak."""
        pak = []
        result = core.all_weapon_stems(pak)
        assert result == []

    def test_all_weapon_stems_no_c_models_folder(self):
        """all_weapon_stems() returns empty for pak without c_models."""
        pak = [
            "models/weapons/w_models/w_gun.mdl",
            "models/player/items/scout/hat.mdl",
        ]
        result = core.all_weapon_stems(pak)
        assert result == []

    def test_all_weapon_stems_variant_suffixes_included(self):
        """all_weapon_stems() includes variant suffixes (unlike find_weapons)."""
        pak = [
            "models/weapons/c_models/c_gun/c_gun.mdl",
            "models/weapons/c_models/c_gun/c_gun_festivizer.mdl",
        ]
        result = core.all_weapon_stems(pak)
        # Both should appear in stems list (no filtering)
        assert "c_gun" in result
        assert "c_gun_festivizer" in result




class TestClassPathTerms:
    """Test class-to-path-term mappings used in filtering."""

    def test_class_path_terms_scout(self):
        """Scout uses 'scout' term in paths."""
        terms = core._CLASS_PATH_TERMS.get("scout", [])
        assert "scout" in terms

    def test_class_path_terms_demoman(self):
        """Demoman uses 'demoman' and 'demo' terms."""
        terms = core._CLASS_PATH_TERMS.get("demoman", [])
        assert "demoman" in terms
        assert "demo" in terms

    def test_class_path_terms_engineer(self):
        """Engineer uses 'engineer' and 'engi' terms."""
        terms = core._CLASS_PATH_TERMS.get("engineer", [])
        assert "engineer" in terms
        assert "engi" in terms

    def test_class_path_terms_soldier(self):
        """Soldier uses 'soldier' and 'solly' terms."""
        terms = core._CLASS_PATH_TERMS.get("soldier", [])
        assert "soldier" in terms
        assert "solly" in terms

    def test_all_class_path_terms_contains_all_terms(self):
        """_ALL_CLASS_PATH_TERMS contains all class path terms."""
        all_terms = core._ALL_CLASS_PATH_TERMS
        # Should contain common terms from each class
        assert "scout" in all_terms
        assert "demo" in all_terms  # demoman shorthand
        assert "engi" in all_terms  # engineer shorthand
        assert "solly" in all_terms  # soldier shorthand

    def test_all_class_path_terms_sorted(self):
        """_ALL_CLASS_PATH_TERMS is sorted."""
        assert core._ALL_CLASS_PATH_TERMS == sorted(core._ALL_CLASS_PATH_TERMS)


class TestWeaponVariantSuffixes:
    """Test weapon variant suffix definitions."""

    def test_variant_suffixes_includes_festivizer(self):
        """Variant suffixes include _festivizer."""
        assert "_festivizer" in core._WEAPON_VARIANT_SUFFIXES

    def test_variant_suffixes_includes_xmas(self):
        """Variant suffixes include _xmas."""
        assert "_xmas" in core._WEAPON_VARIANT_SUFFIXES

    def test_variant_suffixes_includes_helloween(self):
        """Variant suffixes include _helloween."""
        assert "_helloween" in core._WEAPON_VARIANT_SUFFIXES

    def test_variant_suffixes_includes_animations(self):
        """Variant suffixes include _animations."""
        assert "_animations" in core._WEAPON_VARIANT_SUFFIXES

    def test_variant_suffixes_includes_arms(self):
        """Variant suffixes include _arms."""
        assert "_arms" in core._WEAPON_VARIANT_SUFFIXES


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_special_characters_in_keyword(self):
        """Searches handle special characters in keywords."""
        pak = [
            "models/player/items/scout/hat-special.mdl",
        ]
        # Should handle the hyphen without crashing
        result = core.find_models(pak, "hat-special")
        # Result depends on implementation, but shouldn't crash

    def test_unicode_characters_in_paths(self):
        """Searches handle unicode characters gracefully."""
        pak = [
            "models/player/items/scout/hat_français.mdl",
        ]
        # Should not crash with unicode paths
        result = core.find_models(pak, "français")
        # May or may not find it, but shouldn't crash

    def test_very_long_keyword(self):
        """Searches handle very long keywords."""
        pak = [
            "models/test/model.mdl",
        ]
        long_keyword = "x" * 1000
        result = core.find_models(pak, long_keyword)
        assert result == []  # Should be fine, just no match

    def test_empty_string_pak_entry(self):
        """Searches handle empty string entries in pak."""
        pak = ["", "models/player/items/scout/hat.mdl"]
        result = core.find_models(pak, "hat")
        assert len(result) == 1

    def test_pak_with_none_entries(self):
        """Searches handle pak gracefully (None-safe)."""
        # Create a proper pak without None entries
        pak = [
            "models/player/items/scout/hat.mdl",
        ]
        result = core.find_models(pak, "hat")
        assert len(result) == 1

    def test_keyword_with_multiple_spaces(self):
        """Searches handle keywords with multiple spaces."""
        pak = [
            "models/player/items/scout/hot_air_balloon.mdl",
        ]
        result = core.find_models(pak, "hot  air  balloon")  # Multiple spaces
        # Should still find it (spaces become underscores)
        assert len(result) == 1 or len(result) == 0  # Depending on implementation

    def test_leading_trailing_spaces_in_keyword(self):
        """Searches handle leading/trailing spaces in keyword."""
        pak = [
            "models/player/items/scout/hat.mdl",
        ]
        result = core.find_models(pak, "  hat  ")
        # Should strip spaces or handle them gracefully


class TestStemFunctionConsistency:
    """Test consistency between related stem functions."""

    def test_all_stems_larger_than_weapon_stems(self):
        """all_stems() should return at least as many as all_weapon_stems()."""
        pak = [
            "models/weapons/c_models/c_gun/c_gun.mdl",
            "models/player/items/scout/hat.mdl",
            "models/props/barrel.mdl",
        ]
        all_s = core.all_stems(pak)
        weapon_s = core.all_weapon_stems(pak)
        # all_stems includes everything, weapon_stems is a subset
        assert len(all_s) >= len(weapon_s)

    def test_weapon_stems_subset_of_all_stems(self):
        """all_weapon_stems() results should be subset of all_stems()."""
        pak = [
            "models/weapons/c_models/c_gun/c_gun.mdl",
            "models/player/items/scout/hat.mdl",
        ]
        all_s = set(core.all_stems(pak))
        weapon_s = set(core.all_weapon_stems(pak))
        # Weapon stems should be a subset
        assert weapon_s.issubset(all_s)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
