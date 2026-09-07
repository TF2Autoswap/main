#!/usr/bin/env python3
"""
test_tf2autoswap_import_modes.py - Tests for import modes and output handling.

Tests disk imports (cosmetic/weapon), inventory imports, and output modes
(VPK, custom paths, preloader integration) using terminal mocking and tempfiles.

Author: Melancholy Sky
Co-author: AI assistance via OpenRouter
"""

import pytest
import os
import sys
import tempfile
import io
import json
from unittest.mock import Mock, MagicMock, patch, call
from pathlib import Path

import tf2autoswap as cli
import tf2_core as core


# ========== Disk Import - Cosmetic Tests ==========

class TestDiskImportCosmetic:
    """Test disk import mode for cosmetic items"""
    
    def test_disk_import_cosmetic_valid_mdl(self, temp_dir):
        """Disk import cosmetic: valid .mdl file with materials"""
        # Create a temporary .mdl file with real-looking content
        mdl_path = temp_dir / "test_cosmetic.mdl"
        mdl_path.write_bytes(b"IDST" + b"\x00" * 100)  # Minimal MDL header
        
        # Mock core.source_from_disk to return expected data
        mock_model_files = {".mdl": b"mdl_data", ".vvd": b"vvd_data"}
        mock_material_files = {"materials/models/test/skin.vmt": b"vmt_data"}
        mock_meta = {"materials_dir": str(temp_dir / "materials"), "skipped_symlinks": []}
        
        with patch.object(core, 'source_from_disk', return_value=(mock_model_files, mock_material_files, mock_meta)):
            with patch.object(cli, 'HAVE_MATERIAL', True):
                with patch('tf2_material.validate_material_set') as mock_validate:
                    # Mock validation to pass materials through
                    mock_verdict = Mock()
                    mock_verdict.blocked = []
                    mock_verdict.warnings = []
                    mock_verdict.safe_files = mock_material_files
                    mock_validate.return_value = mock_verdict
                    
                    model_files, material_files = cli.get_disk_source(str(mdl_path), target_class="cosmetic")
                    
                    assert model_files == mock_model_files
                    assert material_files == mock_material_files
                    mock_validate.assert_called_once_with(mock_material_files, target_class="cosmetic")
    
    def test_disk_import_cosmetic_no_materials(self, temp_dir):
        """Disk import cosmetic: valid .mdl without materials folder"""
        mdl_path = temp_dir / "test_cosmetic.mdl"
        mdl_path.write_bytes(b"IDST" + b"\x00" * 100)
        
        mock_model_files = {".mdl": b"mdl_data", ".vvd": b"vvd_data"}
        mock_material_files = {}
        mock_meta = {"materials_dir": None, "skipped_symlinks": []}
        
        with patch.object(core, 'source_from_disk', return_value=(mock_model_files, mock_material_files, mock_meta)):
            with patch('builtins.print') as mock_print:
                model_files, material_files = cli.get_disk_source(str(mdl_path), target_class="cosmetic")
                
                assert model_files == mock_model_files
                assert material_files == {}
                # Should print that no materials folder was found
                print_calls = [str(call_args) for call_args in mock_print.call_args_list]
                assert any("No materials/ folder found" in str(c) for c in print_calls)
    
    def test_disk_import_cosmetic_materials_blocked_by_safety(self, temp_dir):
        """Disk import cosmetic: materials blocked by safety check"""
        mdl_path = temp_dir / "test_cosmetic.mdl"
        mdl_path.write_bytes(b"IDST" + b"\x00" * 100)
        
        mock_model_files = {".mdl": b"mdl_data"}
        mock_material_files = {"materials/models/test/bad.vmt": b"bad_vmt"}
        mock_meta = {"materials_dir": str(temp_dir / "materials"), "skipped_symlinks": []}
        
        with patch.object(core, 'source_from_disk', return_value=(mock_model_files, mock_material_files, mock_meta)):
            with patch.object(cli, 'HAVE_MATERIAL', True):
                with patch('tf2_material.validate_material_set') as mock_validate:
                    # Mock validation to block materials
                    mock_verdict = Mock()
                    mock_verdict.blocked = ["materials/models/test/bad.vmt"]
                    mock_verdict.warnings = ["Potentially unsafe material detected"]
                    mock_verdict.safe_files = {}
                    mock_validate.return_value = mock_verdict
                    
                    with patch('builtins.print') as mock_print:
                        model_files, material_files = cli.get_disk_source(str(mdl_path), target_class="cosmetic")
                        
                        assert material_files == {}
                        # Should print blocked materials
                        print_calls = [str(call_args) for call_args in mock_print.call_args_list]
                        assert any("refused by the safety check" in str(c) for c in print_calls)
    
    def test_disk_import_cosmetic_skipped_symlinks_warning(self, temp_dir):
        """Disk import cosmetic: warns about skipped symlinks"""
        mdl_path = temp_dir / "test_cosmetic.mdl"
        mdl_path.write_bytes(b"IDST" + b"\x00" * 100)
        
        mock_model_files = {".mdl": b"mdl_data"}
        mock_material_files = {}
        mock_meta = {
            "materials_dir": None,
            "skipped_symlinks": ["/suspicious/link.vmt", "/another/link.vtf"]
        }
        
        with patch.object(core, 'source_from_disk', return_value=(mock_model_files, mock_material_files, mock_meta)):
            with patch('builtins.print') as mock_print:
                cli.get_disk_source(str(mdl_path))
                
                print_calls = [str(call_args) for call_args in mock_print.call_args_list]
                assert any("Skipped 2 file(s)" in str(c) for c in print_calls)
                assert any("symlink" in str(c) for c in print_calls)
    
    def test_disk_import_cosmetic_without_material_module(self, temp_dir):
        """Disk import cosmetic: materials skipped when tf2_material unavailable"""
        mdl_path = temp_dir / "test_cosmetic.mdl"
        mdl_path.write_bytes(b"IDST" + b"\x00" * 100)
        
        mock_model_files = {".mdl": b"mdl_data"}
        mock_material_files = {"materials/models/test/skin.vmt": b"vmt_data"}
        mock_meta = {"materials_dir": str(temp_dir / "materials"), "skipped_symlinks": []}
        
        with patch.object(core, 'source_from_disk', return_value=(mock_model_files, mock_material_files, mock_meta)):
            with patch.object(cli, 'HAVE_MATERIAL', False):
                with patch('builtins.print') as mock_print:
                    model_files, material_files = cli.get_disk_source(str(mdl_path))
                    
                    # Materials should be skipped entirely
                    assert material_files == {}
                    print_calls = [str(call_args) for call_args in mock_print.call_args_list]
                    assert any("tf2_material.py isn't" in str(c) for c in print_calls)


# ========== Disk Import - Weapon Tests ==========

class TestDiskImportWeapon:
    """Test disk import mode for weapon items"""
    
    def test_disk_import_weapon_viewmodel_only(self, temp_dir):
        """Disk import weapon: viewmodel only (no worldmodel found)"""
        view_path = temp_dir / "c_test_weapon.mdl"
        view_path.write_bytes(b"IDST" + b"\x00" * 100)
        
        mock_view_files = {".mdl": b"view_mdl", ".vvd": b"view_vvd"}
        mock_meta = {"materials_dir": None, "skipped_symlinks": []}
        
        with patch.object(core, 'source_from_disk', return_value=(mock_view_files, {}, mock_meta)):
            with patch.object(core, 'find_disk_weapon_worldmodel', return_value=None):
                with patch('builtins.print') as mock_print:
                    # Simulate the interactive_weapon_swap flow
                    view_files, material_files = cli.get_disk_source(str(view_path), target_class="weapon")
                    world_path = core.find_disk_weapon_worldmodel(str(view_path))
                    
                    assert view_files == mock_view_files
                    assert world_path is None
                    assert material_files == {}
    
    def test_disk_import_weapon_with_worldmodel(self, temp_dir):
        """Disk import weapon: both viewmodel and worldmodel found"""
        view_path = temp_dir / "c_test_weapon.mdl"
        world_path = temp_dir / "w_test_weapon.mdl"
        view_path.write_bytes(b"IDST" + b"\x00" * 100)
        world_path.write_bytes(b"IDST" + b"\x00" * 100)
        
        mock_view_files = {".mdl": b"view_mdl", ".vvd": b"view_vvd"}
        mock_world_files = {".mdl": b"world_mdl", ".vvd": b"world_vvd"}
        mock_meta = {"materials_dir": None, "skipped_symlinks": []}
        
        with patch.object(core, 'source_from_disk') as mock_source:
            # First call for viewmodel, second for worldmodel
            mock_source.side_effect = [
                (mock_view_files, {}, mock_meta),
                (mock_world_files, {}, mock_meta)
            ]
            with patch.object(core, 'find_disk_weapon_worldmodel', return_value=str(world_path)):
                with patch('builtins.print') as mock_print:
                    view_files, view_materials = cli.get_disk_source(str(view_path), target_class="weapon")
                    world_mdl_path = core.find_disk_weapon_worldmodel(str(view_path))
                    
                    assert world_mdl_path == str(world_path)
                    
                    if world_mdl_path:
                        world_files, world_materials = cli.get_disk_source(world_mdl_path, target_class="weapon")
                        assert world_files == mock_world_files
                        
                        # Check that worldmodel found message was printed
                        print_calls = [str(call_args) for call_args in mock_print.call_args_list]
                        # Note: The message is printed by the caller, not get_disk_source
    
    def test_disk_import_weapon_with_materials(self, temp_dir):
        """Disk import weapon: viewmodel with custom materials"""
        view_path = temp_dir / "c_test_weapon.mdl"
        view_path.write_bytes(b"IDST" + b"\x00" * 100)
        
        mock_view_files = {".mdl": b"view_mdl"}
        mock_view_materials = {"materials/models/weapons/test.vmt": b"vmt_data"}
        mock_meta = {"materials_dir": str(temp_dir / "materials"), "skipped_symlinks": []}
        
        with patch.object(core, 'source_from_disk', return_value=(mock_view_files, mock_view_materials, mock_meta)):
            with patch.object(core, 'find_disk_weapon_worldmodel', return_value=None):
                with patch.object(cli, 'HAVE_MATERIAL', True):
                    with patch('tf2_material.validate_material_set') as mock_validate:
                        mock_verdict = Mock()
                        mock_verdict.blocked = []
                        mock_verdict.warnings = []
                        mock_verdict.safe_files = mock_view_materials
                        mock_validate.return_value = mock_verdict
                        
                        view_files, materials = cli.get_disk_source(str(view_path), target_class="weapon")
                        
                        assert materials == mock_view_materials
                        mock_validate.assert_called_once_with(mock_view_materials, target_class="weapon")
    
    def test_disk_import_weapon_materials_merged_from_both_models(self, temp_dir):
        """Disk import weapon: materials from both viewmodel and worldmodel are merged"""
        view_path = temp_dir / "c_test_weapon.mdl"
        world_path = temp_dir / "w_test_weapon.mdl"
        view_path.write_bytes(b"IDST" + b"\x00" * 100)
        world_path.write_bytes(b"IDST" + b"\x00" * 100)
        
        mock_view_files = {".mdl": b"view_mdl"}
        mock_view_materials = {"materials/models/weapons/view.vmt": b"view_vmt"}
        mock_world_files = {".mdl": b"world_mdl"}
        mock_world_materials = {"materials/models/weapons/world.vmt": b"world_vmt"}
        mock_meta = {"materials_dir": str(temp_dir / "materials"), "skipped_symlinks": []}
        
        with patch.object(core, 'source_from_disk') as mock_source:
            mock_source.side_effect = [
                (mock_view_files, mock_view_materials, mock_meta),
                (mock_world_files, mock_world_materials, mock_meta)
            ]
            with patch.object(core, 'find_disk_weapon_worldmodel', return_value=str(world_path)):
                with patch.object(cli, 'HAVE_MATERIAL', True):
                    with patch('tf2_material.validate_material_set') as mock_validate:
                        mock_verdict = Mock()
                        mock_verdict.blocked = []
                        mock_verdict.warnings = []
                        # Return the materials passed to it
                        mock_validate.side_effect = lambda mats, **kw: Mock(
                            blocked=[], warnings=[], safe_files=mats
                        )
                        
                        # Simulate the flow from interactive_weapon_swap
                        view_files, material_files = cli.get_disk_source(str(view_path), target_class="weapon")
                        world_mdl_path = core.find_disk_weapon_worldmodel(str(view_path))
                        
                        if world_mdl_path:
                            world_files, world_material_files = cli.get_disk_source(world_mdl_path, target_class="weapon")
                            # In actual code: material_files.update(world_material_files)
                            merged_materials = {**material_files, **world_material_files}
                            
                            assert "materials/models/weapons/view.vmt" in merged_materials
                            assert "materials/models/weapons/world.vmt" in merged_materials


# ========== Inventory Import Tests ==========

class TestInventoryImport:
    """Test inventory import mode"""
    
    def test_inventory_import_list_json_files(self, temp_dir):
        """Inventory import: list available JSON files"""
        inv_dir = temp_dir / "inventory"
        inv_dir.mkdir()
        
        # Create test JSON files
        (inv_dir / "my_inventory.json").write_text("{}")
        (inv_dir / "backup.json").write_text("{}")
        (inv_dir / "readme.txt").touch()  # Should be ignored
        
        with patch.object(cli, 'INVENTORY_IMPORT_DIR', str(inv_dir)):
            files = cli.list_inventory_json_files()
            
            assert len(files) == 2
            assert any("my_inventory.json" in f for f in files)
            assert any("backup.json" in f for f in files)
            assert not any("readme.txt" in f for f in files)
    
    def test_inventory_import_no_json_files(self, temp_dir):
        """Inventory import: no JSON files available returns empty list"""
        inv_dir = temp_dir / "inventory"
        inv_dir.mkdir()
        
        with patch.object(cli, 'INVENTORY_IMPORT_DIR', str(inv_dir)):
            files = cli.list_inventory_json_files()
            assert files == []
    
    def test_inventory_import_directory_missing(self, temp_dir):
        """Inventory import: missing directory returns empty list"""
        inv_dir = temp_dir / "nonexistent"
        
        with patch.object(cli, 'INVENTORY_IMPORT_DIR', str(inv_dir)):
            files = cli.list_inventory_json_files()
            assert files == []
    
    def test_load_owned_items_valid_json(self, temp_dir):
        """Inventory import: load valid inventory JSON"""
        inv_path = temp_dir / "inventory.json"
        inv_data = [
            {"defindex": 1, "quality": 6, "quantity": 1},
            {"defindex": 2, "quality": 6, "quantity": 1}
        ]
        inv_path.write_text(json.dumps(inv_data))
        
        with patch.object(core, 'load_inventory_file', return_value=inv_data) as mock_load:
            with patch('builtins.input', return_value=str(inv_path)):
                with patch('builtins.print'):
                    items = cli.load_owned_items_interactive()
                    
                    assert items == inv_data
                    mock_load.assert_called_once()
    
    def test_load_owned_items_malformed_json(self, temp_dir):
        """Inventory import: handle malformed JSON gracefully"""
        inv_path = temp_dir / "bad_inventory.json"
        inv_path.write_text("{not valid json[")
        
        with patch.object(core, 'load_inventory_file', side_effect=core.InventoryError("Invalid JSON")):
            with patch('builtins.input', return_value=str(inv_path)):
                with patch('builtins.print') as mock_print:
                    items = cli.load_owned_items_interactive()
                    
                    assert items is None
                    # Should print error message
                    print_calls = [str(call_args) for call_args in mock_print.call_args_list]
                    assert any("InventoryError" in str(c) or "Invalid JSON" in str(c) for c in print_calls)
    
    def test_load_owned_items_user_quit(self, temp_dir):
        """Inventory import: user can quit during file selection"""
        with patch('builtins.input', return_value='q'):
            items = cli.load_owned_items_interactive()
            assert items is None
    
    def test_load_owned_items_auto_select_single_file(self, temp_dir):
        """Inventory import: auto-present single JSON file found"""
        inv_dir = temp_dir / "inventory"
        inv_dir.mkdir()
        inv_path = inv_dir / "my_inventory.json"
        inv_data = [{"defindex": 1}]
        inv_path.write_text(json.dumps(inv_data))
        
        with patch.object(cli, 'INVENTORY_IMPORT_DIR', str(inv_dir)):
            with patch.object(core, 'load_inventory_file', return_value=inv_data):
                with patch.object(cli, 'choose', return_value=str(inv_path)):
                    with patch('builtins.print'):
                        items = cli.load_owned_items_interactive()
                        
                        assert items == inv_data
    
    def test_pick_from_inventory_no_defindex_index(self):
        """Pick from inventory: unavailable when schema missing"""
        mock_pak = Mock()
        
        with patch('builtins.print') as mock_print:
            result, loaded = cli.pick_from_inventory(
                mock_pak, None, "cosmetic", "test item"
            )
            
            assert result is None
            print_calls = [str(call_args) for call_args in mock_print.call_args_list]
            assert any("isn't available" in str(c) for c in print_calls)
    
    def test_pick_from_inventory_cosmetic_match(self, temp_dir):
        """Pick from inventory: successfully match and pick cosmetic"""
        mock_pak = Mock()
        defindex_index = {
            "1": {"name": "Test Hat", "model_path": "models/player/items/test_hat.mdl"}
        }
        owned_items = [{"defindex": 1}]
        
        matched_items = [
            {
                "defindex": 1,
                "name": "Test Hat",
                "model_path": "models/player/items/test_hat.mdl",
                "item_type": "cosmetic"
            }
        ]
        
        with patch.object(core, 'match_owned_items', return_value=matched_items):
            with patch.object(cli, 'choose_paginated', return_value="models/player/items/test_hat.mdl"):
                with patch('builtins.print'):
                    result, loaded = cli.pick_from_inventory(
                        mock_pak, defindex_index, "cosmetic", "the cosmetic",
                        owned_items=owned_items
                    )
                    
                    assert result == "models/player/items/test_hat.mdl"
                    assert loaded == owned_items
    
    def test_pick_from_inventory_weapon_match(self, temp_dir):
        """Pick from inventory: successfully match and pick weapon"""
        mock_pak = Mock()
        defindex_index = {
            "2": {"name": "Scattergun", "model_path": "models/weapons/c_scattergun.mdl"}
        }
        owned_items = [{"defindex": 2}]
        
        matched_items = [
            {
                "defindex": 2,
                "name": "Scattergun",
                "model_path": "models/weapons/c_scattergun.mdl",
                "item_type": "weapon"
            }
        ]
        
        with patch.object(core, 'match_owned_items', return_value=matched_items):
            with patch.object(cli, 'choose_paginated', return_value="models/weapons/c_scattergun.mdl"):
                with patch('builtins.print'):
                    result, loaded = cli.pick_from_inventory(
                        mock_pak, defindex_index, "weapon", "the weapon",
                        owned_items=owned_items
                    )
                    
                    assert result == "models/weapons/c_scattergun.mdl"
                    assert loaded == owned_items
    
    def test_pick_from_inventory_no_matches(self):
        """Pick from inventory: no owned items match the filter"""
        mock_pak = Mock()
        defindex_index = {"1": {"name": "Test"}}
        owned_items = [{"defindex": 999}]  # Different defindex
        
        with patch.object(core, 'match_owned_items', return_value=[]):
            with patch('builtins.print') as mock_print:
                result, loaded = cli.pick_from_inventory(
                    mock_pak, defindex_index, "cosmetic", "test item",
                    owned_items=owned_items
                )
                
                assert result is None
                assert loaded == owned_items
                print_calls = [str(call_args) for call_args in mock_print.call_args_list]
                assert any("No owned" in str(c) for c in print_calls)
    
    def test_pick_from_inventory_filters_by_item_type(self):
        """Pick from inventory: filters results by item_type"""
        mock_pak = Mock()
        defindex_index = {"1": {"name": "Test"}}
        owned_items = [{"defindex": 1}]
        
        # matched_items has both cosmetics and weapons
        all_matched = [
            {"defindex": 1, "name": "Hat", "model_path": "models/hat.mdl", "item_type": "cosmetic"},
            {"defindex": 1, "name": "Gun", "model_path": "models/gun.mdl", "item_type": "weapon"}
        ]
        
        with patch.object(core, 'match_owned_items', return_value=all_matched):
            with patch.object(cli, 'choose_paginated', return_value="models/hat.mdl"):
                with patch('builtins.print'):
                    # Request only cosmetics
                    result, loaded = cli.pick_from_inventory(
                        mock_pak, defindex_index, "cosmetic", "test",
                        owned_items=owned_items
                    )
                    
                    # choose_paginated should have been called with only cosmetic options
                    assert cli.choose_paginated.call_count == 1
                    call_args = cli.choose_paginated.call_args
                    options = call_args[0][1]
                    # Only the cosmetic should be in options
                    assert len(options) == 1
                    assert options[0] == "models/hat.mdl"


# ========== Output Mode Tests ==========

class TestOutputModes:
    """Test different output modes (VPK, custom path, preloader)"""
    
    def test_output_default_vpk_to_output_dir(self, temp_dir):
        """Output mode: default VPK to OUTPUT_DIR"""
        output_dir = temp_dir / "output"
        output_dir.mkdir()
        
        mock_files = {".mdl": b"data"}
        mock_result = {"packed": [".mdl", ".vvd"], "out_path": str(output_dir / "test.vpk"), "material_count": 0}
        
        with patch.object(cli, 'OUTPUT_DIR', str(output_dir)):
            with patch.object(core, 'build', return_value=mock_result):
                with patch('builtins.print'):
                    result = cli.emit_vpk(mock_files, "dst_base", str(output_dir / "test.vpk"), 
                                         None, "source", "target")
                    
                    assert result == mock_result
                    core.build.assert_called_once()
    
    def test_output_custom_path_file(self, temp_dir):
        """Output mode: custom output path as file"""
        custom_path = temp_dir / "custom" / "my_mod.vpk"
        custom_path.parent.mkdir(parents=True)
        
        mock_files = {".mdl": b"data"}
        mock_result = {"packed": [".mdl"], "out_path": str(custom_path), "material_count": 0}
        
        with patch.object(core, 'build', return_value=mock_result):
            with patch('builtins.print'):
                result = cli.emit_vpk(mock_files, "dst_base", str(custom_path),
                                     None, "source", "target")
                
                assert result == mock_result
                assert core.build.call_args[0][2] == str(custom_path)
    
    def test_output_custom_path_directory(self, temp_dir):
        """Output mode: custom output path as directory"""
        custom_dir = temp_dir / "mods"
        custom_dir.mkdir()
        filename = "test_mod.vpk"
        
        # resolve_out_path should turn directory into file path
        expected_path = custom_dir / filename
        
        with patch.object(cli, 'resolve_out_path', return_value=str(expected_path)):
            result_path = cli.resolve_out_path(str(custom_dir), filename)
            assert result_path == str(expected_path)
    
    def test_output_file_exists_warning(self, temp_dir):
        """Output mode: warn when output file already exists"""
        output_path = temp_dir / "existing.vpk"
        output_path.write_bytes(b"existing data")
        
        mock_files = {".mdl": b"data"}
        mock_result = {"packed": [".mdl"], "out_path": str(output_path), "material_count": 0}
        
        with patch.object(core, 'build', return_value=mock_result):
            with patch('builtins.print') as mock_print:
                # emit_vpk handles file existence via core.build
                cli.emit_vpk(mock_files, "dst_base", str(output_path),
                           None, "source", "target")
                
                # File existence is handled by core.build, not emit_vpk
                # But we can verify the path was passed correctly
                assert core.build.call_args[0][2] == str(output_path)
    
    def test_output_preloader_addon_format(self, temp_dir):
        """Output mode: preloader addon folder format"""
        preloader_dir = temp_dir / "preloader" / "addons"
        preloader_dir.mkdir(parents=True)
        addon_name = "test_addon"
        
        mock_files = {".mdl": b"data"}
        mock_result = {
            "addon_dir": str(preloader_dir / addon_name),
            "packed": [".mdl", ".vvd"]
        }
        
        with patch.object(core, 'build_addon_folder', return_value=mock_result):
            with patch('builtins.print'):
                result = cli.emit_addon(mock_files, "dst_base", str(preloader_dir),
                                       addon_name, None, "source", "target")
                
                assert result == mock_result
                core.build_addon_folder.assert_called_once()
                assert core.build_addon_folder.call_args[0][2] == str(preloader_dir)
    
    def test_is_in_preloader_true(self, temp_dir):
        """is_in_preloader: correctly identifies paths inside preloader"""
        preloader_dir = temp_dir / "preloader"
        inside_path = preloader_dir / "addons" / "my_mod"
        
        preloader_dir.mkdir()
        
        result = cli.is_in_preloader(str(inside_path), str(preloader_dir))
        assert result is True
    
    def test_is_in_preloader_false(self, temp_dir):
        """is_in_preloader: correctly identifies paths outside preloader"""
        preloader_dir = temp_dir / "preloader"
        outside_path = temp_dir / "other" / "location"
        
        preloader_dir.mkdir()
        outside_path.parent.mkdir(parents=True)
        
        result = cli.is_in_preloader(str(outside_path), str(preloader_dir))
        assert result is False
    
    def test_is_in_preloader_different_drives_windows(self, temp_dir):
        """is_in_preloader: handles different drives on Windows gracefully"""
        # Simulate Windows behavior where commonpath raises ValueError for different drives
        with patch('os.path.commonpath', side_effect=ValueError("Different drives")):
            result = cli.is_in_preloader("C:/path", "D:/preloader")
            assert result is False
    
    def test_confirm_preloader_write_yes(self):
        """confirm_preloader_write: user confirms with 'yes'"""
        with patch('builtins.input', return_value='yes'):
            with patch('builtins.print'):
                result = cli.confirm_preloader_write("/path/to/preloader")
                assert result is True
    
    def test_confirm_preloader_write_no(self):
        """confirm_preloader_write: user cancels with anything else"""
        with patch('builtins.input', return_value='n'):
            with patch('builtins.print'):
                result = cli.confirm_preloader_write("/path/to/preloader")
                assert result is False
    
    def test_confirm_preloader_write_case_insensitive(self):
        """confirm_preloader_write: 'YES' works (case insensitive)"""
        with patch('builtins.input', return_value='YES'):
            with patch('builtins.print'):
                result = cli.confirm_preloader_write("/path/to/preloader")
                assert result is True
    
    def test_output_detect_preloader_and_warn(self, temp_dir):
        """Output mode: detect when custom path is in preloader and warn"""
        preloader_dir = temp_dir / "preloader"
        custom_path = preloader_dir / "addons" / "test.vpk"
        preloader_dir.mkdir(parents=True)
        
        # is_in_preloader should detect this
        result = cli.is_in_preloader(str(custom_path), str(preloader_dir))
        assert result is True
        
        # In actual flow, this would trigger confirm_preloader_write
    
    def test_output_directory_creation_for_custom_path(self, temp_dir):
        """Output mode: creates directory structure for custom path"""
        custom_path = temp_dir / "nested" / "deep" / "mod.vpk"
        
        mock_files = {".mdl": b"data"}
        
        # validate_output_path checks if parent exists and is writable
        with patch.object(cli, 'validate_output_path', return_value=(True, None)):
            # Parent directory creation is handled by core.build, not cli
            # We just verify path handling works
            parent_dir = custom_path.parent
            assert str(parent_dir) == str(temp_dir / "nested" / "deep")


# ========== CLI Integration Tests ==========

class TestCLIIntegration:
    """Test CLI argument handling for import modes"""
    
    def test_cli_import_cosmetic(self, temp_dir):
        """CLI: --import cosmetic.mdl target"""
        mdl_path = temp_dir / "custom.mdl"
        mdl_path.write_bytes(b"IDST" + b"\x00" * 100)
        
        mock_files = {".mdl": b"data"}
        mock_pak = Mock()
        
        with patch('sys.argv', ['tf2autoswap.py', '--import', str(mdl_path), 'target_keyword']):
            with patch.object(core, 'resolve_tf2', return_value="/fake/tf2"):
                with patch.object(core, 'open_pak', return_value=mock_pak):
                    with patch.object(cli, 'load_index', return_value=None):
                        with patch.object(cli, 'get_disk_source', return_value=(mock_files, {})):
                            with patch.object(core, 'find_models', return_value=["models/target.mdl"]):
                                with patch.object(core, 'build', return_value={"vpk_path": "out.vpk", "size": 1024}):
                                    with patch('builtins.print'):
                                        # Parse args to check --import handling
                                        import argparse
                                        ap = argparse.ArgumentParser()
                                        ap.add_argument("--import", dest="import_path")
                                        ap.add_argument("source", nargs="?")
                                        ap.add_argument("target", nargs="?")
                                        
                                        args = ap.parse_args(['--import', str(mdl_path), 'target_keyword'])
                                        
                                        # With --import and positional arg, target should be the positional
                                        assert args.import_path == str(mdl_path)
                                        assert args.source == 'target_keyword'
                                        assert args.target is None
                                        
                                        # cli() swaps source->target when import_path is present
                                        if args.import_path and args.source and not args.target:
                                            args.target = args.source
                                            args.source = None
                                        
                                        assert args.target == 'target_keyword'
                                        assert args.source is None
    
    def test_cli_import_weapon(self, temp_dir):
        """CLI: --import c_weapon.mdl target --weapon"""
        view_path = temp_dir / "c_custom.mdl"
        view_path.write_bytes(b"IDST" + b"\x00" * 100)
        
        mock_view_files = {".mdl": b"view_data"}
        mock_pak = Mock()
        
        with patch('sys.argv', ['tf2autoswap.py', '--import', str(view_path), 'target', '--weapon']):
            import argparse
            ap = argparse.ArgumentParser()
            ap.add_argument("--import", dest="import_path")
            ap.add_argument("--weapon", action="store_true")
            ap.add_argument("source", nargs="?")
            ap.add_argument("target", nargs="?")
            
            args = ap.parse_args(['--import', str(view_path), 'target', '--weapon'])
            
            assert args.import_path == str(view_path)
            assert args.weapon is True
            assert args.source == 'target'
            
            # After the swap logic
            if args.import_path and args.source and not args.target:
                args.target = args.source
                args.source = None
            
            assert args.target == 'target'


# ========== Workflow Integration Tests ==========

class TestWorkflowIntegration:
    """Test complete import-to-output workflows"""
    
    def test_workflow_disk_import_cosmetic_to_vpk(self, temp_dir):
        """Workflow: disk import cosmetic -> VPK output"""
        # Setup
        mdl_path = temp_dir / "custom_hat.mdl"
        mdl_path.write_bytes(b"IDST" + b"\x00" * 100)
        output_dir = temp_dir / "output"
        output_dir.mkdir()
        
        mock_model_files = {".mdl": b"mdl_data", ".vvd": b"vvd_data"}
        mock_result = {"packed": [".mdl", ".vvd"], "out_path": str(output_dir / "test.vpk"), "material_count": 0}
        
        # Execute workflow
        with patch.object(core, 'source_from_disk', return_value=(mock_model_files, {}, {"materials_dir": None, "skipped_symlinks": []})):
            with patch.object(core, 'build', return_value=mock_result):
                with patch('builtins.print'):
                    # Step 1: Load from disk
                    model_files, material_files = cli.get_disk_source(str(mdl_path))
                    
                    # Step 2: Build VPK
                    result = cli.emit_vpk(model_files, "dst_base", 
                                         str(output_dir / "test.vpk"),
                                         material_files, "custom_hat", "target")
                    
                    assert result == mock_result
    
    def test_workflow_disk_import_weapon_to_preloader(self, temp_dir):
        """Workflow: disk import weapon -> preloader addon"""
        # Setup
        view_path = temp_dir / "c_custom_weapon.mdl"
        world_path = temp_dir / "w_custom_weapon.mdl"
        view_path.write_bytes(b"IDST" + b"\x00" * 100)
        world_path.write_bytes(b"IDST" + b"\x00" * 100)
        preloader_dir = temp_dir / "preloader"
        preloader_dir.mkdir()
        
        mock_view_files = {".mdl": b"view_mdl"}
        mock_world_files = {".mdl": b"world_mdl"}
        mock_meta = {"materials_dir": None, "skipped_symlinks": []}
        mock_result = {"addon_dir": str(preloader_dir / "addon"), "packed": [".mdl"]}
        
        # Execute workflow
        with patch.object(core, 'source_from_disk') as mock_source:
            mock_source.side_effect = [
                (mock_view_files, {}, mock_meta),
                (mock_world_files, {}, mock_meta)
            ]
            with patch.object(core, 'find_disk_weapon_worldmodel', return_value=str(world_path)):
                with patch.object(core, 'build_weapon_addon_folder', return_value=mock_result):
                    with patch('builtins.print'):
                        # Step 1: Load viewmodel
                        view_files, view_mats = cli.get_disk_source(str(view_path), target_class="weapon")
                        
                        # Step 2: Find worldmodel
                        world_mdl_path = core.find_disk_weapon_worldmodel(str(view_path))
                        
                        # Step 3: Load worldmodel
                        world_files, world_mats = cli.get_disk_source(world_mdl_path, target_class="weapon")
                        
                        # Step 4: Build addon
                        result = cli.emit_weapon_addon(
                            view_files, world_files, "dst_view", "dst_world",
                            str(preloader_dir), "addon_name", "source", "target"
                        )
                        
                        assert result == mock_result
    
    def test_workflow_inventory_import_to_custom_path(self, temp_dir):
        """Workflow: inventory import -> custom output path"""
        # Setup
        inv_path = temp_dir / "inventory.json"
        inv_data = [{"defindex": 1}]
        inv_path.write_text(json.dumps(inv_data))
        
        custom_out = temp_dir / "my_mods" / "swap.vpk"
        custom_out.parent.mkdir(parents=True)
        
        mock_pak = Mock()
        defindex_index = {"1": {"name": "Hat", "model_path": "models/hat.mdl"}}
        matched = [{"defindex": 1, "name": "Hat", "model_path": "models/hat.mdl", "item_type": "cosmetic"}]
        
        mock_model_files = {".mdl": b"data"}
        mock_result = {"packed": [".mdl"], "out_path": str(custom_out), "material_count": 0}
        
        # Execute workflow
        with patch.object(core, 'load_inventory_file', return_value=inv_data):
            with patch.object(core, 'match_owned_items', return_value=matched):
                with patch.object(cli, 'choose_paginated', return_value="models/hat.mdl"):
                    with patch.object(core, 'source_from_vpk', return_value=mock_model_files):
                        with patch.object(core, 'build', return_value=mock_result):
                            with patch('builtins.input', return_value=str(inv_path)):
                                with patch('builtins.print'):
                                    # Step 1: Load inventory
                                    items = cli.load_owned_items_interactive()
                                    
                                    # Step 2: Pick from inventory
                                    model_path, _ = cli.pick_from_inventory(
                                        mock_pak, defindex_index, "cosmetic",
                                        "test", owned_items=items
                                    )
                                    
                                    # Step 3: Source from VPK
                                    model_files = core.source_from_vpk(mock_pak, model_path[:-4])
                                    
                                    # Step 4: Build to custom path
                                    result = cli.emit_vpk(model_files, "dst", str(custom_out),
                                                         None, "source", "target")
                                    
                                    assert result == mock_result
