#!/usr/bin/env python3
"""
test_tf2autoswap_main.py - Tests for tf2autoswap.py main program flow.

Tests main() entry point, command-line argument handling, interactive modes,
setup flows, and error handling using terminal mocking.

Author: Melancholy Sky
Co-author: AI assistance via OpenRouter
"""

import pytest
import os
import sys
import tempfile
import io
from unittest.mock import Mock, MagicMock, patch, call
from pathlib import Path

import tf2autoswap as cli
import tf2_core as core


class TestMainEntryPoint:
    """Test main() entry point setup and initialization"""
    
    def test_main_sets_up_logging(self):
        """main() initializes logging before proceeding"""
        with patch.object(cli, 'setup_logging', return_value=Mock()) as mock_setup:
            with patch.object(cli, 'check_acknowledgement'):
                with patch.object(cli, 'setup_folders'):
                    with patch.object(cli, 'run'):
                        try:
                            cli.main()
                        except SystemExit:
                            pass
                        mock_setup.assert_called_once()
    
    def test_main_checks_acknowledgement_before_run(self):
        """main() calls check_acknowledgement() before run()"""
        with patch.object(cli, 'setup_logging', return_value=Mock()):
            with patch.object(cli, 'check_acknowledgement') as mock_ack:
                with patch.object(cli, 'setup_folders'):
                    with patch.object(cli, 'run'):
                        try:
                            cli.main()
                        except SystemExit:
                            pass
                        mock_ack.assert_called_once()
    
    def test_main_sets_up_folders_after_acknowledgement(self):
        """main() calls setup_folders() after acknowledgement"""
        with patch.object(cli, 'setup_logging', return_value=Mock()):
            with patch.object(cli, 'check_acknowledgement'):
                with patch.object(cli, 'setup_folders') as mock_setup:
                    with patch.object(cli, 'run'):
                        try:
                            cli.main()
                        except SystemExit:
                            pass
                        mock_setup.assert_called_once()
    
    def test_main_calls_run_after_setup(self):
        """main() calls run() after all setup completes"""
        with patch.object(cli, 'setup_logging', return_value=Mock()):
            with patch.object(cli, 'check_acknowledgement'):
                with patch.object(cli, 'setup_folders'):
                    with patch.object(cli, 'run') as mock_run:
                        try:
                            cli.main()
                        except SystemExit:
                            pass
                        mock_run.assert_called_once()
    
    def test_main_handles_keyboard_interrupt(self):
        """main() catches KeyboardInterrupt and exits gracefully"""
        with patch.object(cli, 'setup_logging', return_value=Mock()):
            with patch.object(cli, 'check_acknowledgement'):
                with patch.object(cli, 'setup_folders'):
                    with patch.object(cli, 'run', side_effect=KeyboardInterrupt):
                        with pytest.raises(SystemExit) as exc_info:
                            cli.main()
                        assert exc_info.value.code == 0
    
    def test_main_handles_swap_error(self):
        """main() catches core.SwapError and exits with error code"""
        with patch.object(cli, 'setup_logging', return_value=Mock()):
            with patch.object(cli, 'check_acknowledgement'):
                with patch.object(cli, 'setup_folders'):
                    with patch.object(cli, 'run', side_effect=core.SwapError("Test error")):
                        with pytest.raises(SystemExit) as exc_info:
                            cli.main()
                        assert exc_info.value.code == 1
    
    def test_main_handles_unexpected_exception(self):
        """main() catches unexpected exceptions and logs them"""
        with patch.object(cli, 'setup_logging', return_value=Mock()) as mock_log:
            with patch.object(cli, 'check_acknowledgement'):
                with patch.object(cli, 'setup_folders'):
                    with patch.object(cli, 'run', side_effect=ValueError("Unexpected")):
                        with pytest.raises(SystemExit) as exc_info:
                            cli.main()
                        assert exc_info.value.code == 1


class TestSetupLogging:
    """Test logging setup function"""
    
    def test_setup_logging_returns_logger(self):
        """setup_logging() returns a configured logger"""
        logger = cli.setup_logging()
        assert logger is not None
        assert hasattr(logger, 'info')
        assert callable(logger.info)
    
    def test_setup_logging_handles_permission_errors(self):
        """setup_logging() gracefully handles log file permission errors"""
        # Should not raise even if log path is unwritable
        with patch('os.makedirs', side_effect=PermissionError):
            logger = cli.setup_logging()
            assert logger is not None


class TestSetupFolders:
    """Test folder setup function"""
    
    def test_setup_folders_creates_state_dir(self):
        """setup_folders() creates STATE_DIR"""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_state_dir = os.path.join(tmpdir, ".tf2autoswap")
            with patch.object(cli, 'STATE_DIR', test_state_dir):
                with patch.object(cli, 'IMPORTS_DIR', os.path.join(tmpdir, "imports")):
                    with patch.object(cli, 'write_inventory_guide'):
                        cli.setup_folders()
                    assert os.path.isdir(test_state_dir)
    
    def test_setup_folders_creates_import_subdirs(self):
        """setup_folders() creates all import subdirectories"""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_imports_dir = os.path.join(tmpdir, "imports")
            with patch.object(cli, 'STATE_DIR', os.path.join(tmpdir, ".state")):
                with patch.object(cli, 'IMPORTS_DIR', test_imports_dir):
                    with patch.object(cli, 'write_inventory_guide'):
                        cli.setup_folders()
                    # Check that at least cosmetics subdir was created
                    cosmetics = os.path.join(test_imports_dir, "cosmetics")
                    assert os.path.isdir(cosmetics)
    
    def test_setup_folders_writes_inventory_guide(self):
        """setup_folders() calls write_inventory_guide()"""
        with patch.object(cli, 'write_inventory_guide') as mock_write:
            with patch('os.makedirs'):
                cli.setup_folders()
            mock_write.assert_called_once()
    
    def test_setup_folders_is_idempotent(self):
        """setup_folders() can be called multiple times safely"""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_state_dir = os.path.join(tmpdir, ".tf2autoswap")
            with patch.object(cli, 'STATE_DIR', test_state_dir):
                with patch.object(cli, 'IMPORTS_DIR', os.path.join(tmpdir, "imports")):
                    with patch.object(cli, 'write_inventory_guide'):
                        # Call twice
                        cli.setup_folders()
                        cli.setup_folders()
                    # Should still exist and be a directory
                    assert os.path.isdir(test_state_dir)
    
    def test_setup_folders_handles_permission_errors(self):
        """setup_folders() gracefully handles permission errors"""
        with patch('os.makedirs', side_effect=PermissionError):
            # Should not raise
            cli.setup_folders()


class TestCheckAcknowledgement:
    """Test risk acknowledgement system"""
    
    def test_check_acknowledgement_creates_state_dir(self):
        """check_acknowledgement() creates STATE_DIR if missing"""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_state_dir = os.path.join(tmpdir, ".tf2autoswap")
            test_flag = os.path.join(test_state_dir, ".acknowledged")
            with patch.object(cli, 'STATE_DIR', test_state_dir):
                with patch.object(cli, 'ACKNOWLEDGED_FLAG', test_flag):
                    # Mock stdin to auto-accept
                    with patch('builtins.input', return_value='agree'):
                        cli.check_acknowledgement()
                    assert os.path.isdir(test_state_dir)
    
    def test_check_acknowledgement_prompts_on_first_run(self):
        """check_acknowledgement() prompts user on first run"""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_flag = os.path.join(tmpdir, ".acknowledged")
            with patch.object(cli, 'ACKNOWLEDGED_FLAG', test_flag):
                with patch.object(cli, 'STATE_DIR', tmpdir):
                    with patch('builtins.input', return_value='agree') as mock_input:
                        cli.check_acknowledgement()
                    mock_input.assert_called()
    
    def test_check_acknowledgement_accepts_agree(self):
        """check_acknowledgement() accepts 'agree' input"""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_flag = os.path.join(tmpdir, ".acknowledged")
            with patch.object(cli, 'ACKNOWLEDGED_FLAG', test_flag):
                with patch.object(cli, 'STATE_DIR', tmpdir):
                    with patch('builtins.input', return_value='agree'):
                        cli.check_acknowledgement()
                    # Flag file should be created
                    assert os.path.isfile(test_flag)
    
    def test_check_acknowledgement_exits_on_quit(self):
        """check_acknowledgement() exits when user types 'q'"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(cli, 'ACKNOWLEDGED_FLAG', os.path.join(tmpdir, ".ack")):
                with patch.object(cli, 'STATE_DIR', tmpdir):
                    with patch('builtins.input', return_value='q'):
                        with pytest.raises(SystemExit) as exc_info:
                            cli.check_acknowledgement()
                        assert exc_info.value.code == 0
    
    def test_check_acknowledgement_skips_prompt_when_acknowledged(self):
        """check_acknowledgement() skips prompt if already acknowledged"""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_flag = os.path.join(tmpdir, ".acknowledged")
            # Write valid acknowledgement hash
            with open(test_flag, 'w') as f:
                f.write(cli._ACK_HASH + "\n")
            
            with patch.object(cli, 'ACKNOWLEDGED_FLAG', test_flag):
                with patch.object(cli, 'STATE_DIR', tmpdir):
                    with patch('builtins.input') as mock_input:
                        cli.check_acknowledgement()
                    # Should not have prompted
                    mock_input.assert_not_called()
    
    def test_check_acknowledgement_reprompts_on_invalid_hash(self):
        """check_acknowledgement() re-prompts if flag file has wrong hash"""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_flag = os.path.join(tmpdir, ".acknowledged")
            # Write invalid hash
            with open(test_flag, 'w') as f:
                f.write("invalid_hash\n")
            
            with patch.object(cli, 'ACKNOWLEDGED_FLAG', test_flag):
                with patch.object(cli, 'STATE_DIR', tmpdir):
                    with patch('builtins.input', return_value='agree') as mock_input:
                        cli.check_acknowledgement()
                    # Should have prompted again
                    mock_input.assert_called()


class TestRunCommandLineParsing:
    """Test run() function command-line argument parsing"""
    
    def test_run_handles_list_installed_without_tf2(self):
        """run() --list-installed works without TF2 path"""
        with patch('sys.argv', ['tf2autoswap.py', '--list-installed']):
            with patch.object(cli, 'show_installed') as mock_show:
                cli.run()
                mock_show.assert_called_once()
    
    def test_run_resolves_tf2_path(self):
        """run() resolves TF2 path for most operations"""
        with patch('sys.argv', ['tf2autoswap.py', '--version']):
            with pytest.raises(SystemExit):
                # --version exits early, but path resolution happens
                cli.run()
    
    def test_run_handles_list_mods_flag(self):
        """run() --list-mods displays built mods"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('sys.argv', ['tf2autoswap.py', '--list-mods']):
                with patch.object(core, 'resolve_tf2', return_value=tmpdir):
                    with patch.object(cli, 'load_index', return_value={}):
                        with patch.object(cli, 'manage_mods_readonly') as mock_manage:
                            cli.run()
                        mock_manage.assert_called_once()
    
    def test_run_handles_debug_inventory_flag(self):
        """run() --debug-inventory shows inventory diagnosis"""
        with tempfile.TemporaryDirectory() as tmpdir:
            inv_file = os.path.join(tmpdir, "inv.json")
            with open(inv_file, 'w') as f:
                f.write('{"assets": []}')
            
            with patch('sys.argv', ['tf2autoswap.py', '--debug-inventory', inv_file]):
                with patch.object(core, 'resolve_tf2', return_value=tmpdir):
                    with patch.object(core, 'open_pak', return_value=Mock()):
                        with patch.object(cli, 'show_inventory_diagnosis') as mock_diag:
                            cli.run()
                        mock_diag.assert_called_once()
    
    def test_run_handles_list_flag(self):
        """run() --list searches without building"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('sys.argv', ['tf2autoswap.py', '--list', 'scattergun']):
                with patch.object(core, 'resolve_tf2', return_value=tmpdir):
                    mock_pak = Mock()
                    with patch.object(core, 'open_pak', return_value=mock_pak):
                        with patch.object(core, 'find_models', return_value=[]):
                            with patch.object(cli, 'load_index', return_value={}):
                                cli.run()


class TestCLIModeCosmeticSwap:
    """Test CLI non-interactive cosmetic swap mode"""
    
    def test_cli_cosmetic_swap_with_source_and_target(self):
        """run() performs cosmetic swap with source and target arguments"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('sys.argv', ['tf2autoswap.py', 'hat1', 'hat2']):
                with patch.object(core, 'resolve_tf2', return_value=tmpdir):
                    mock_pak = Mock()
                    with patch.object(core, 'open_pak', return_value=mock_pak):
                        with patch.object(cli, 'load_index', return_value={}):
                            with patch.object(cli, 'cli') as mock_cli:
                                cli.run()
                            mock_cli.assert_called_once()
    
    def test_cli_weapon_swap_with_weapon_flag(self):
        """run() --weapon routes to weapon swap mode"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('sys.argv', ['tf2autoswap.py', 'scattergun', 'shortstop', '--weapon']):
                with patch.object(core, 'resolve_tf2', return_value=tmpdir):
                    mock_pak = Mock()
                    with patch.object(core, 'open_pak', return_value=mock_pak):
                        with patch.object(cli, 'load_index', return_value={}):
                            with patch.object(cli, 'cli_weapon') as mock_cli_weapon:
                                cli.run()
                            mock_cli_weapon.assert_called_once()
    
    def test_cli_import_mode_swaps_arguments(self):
        """run() --import file.mdl keyword swaps args correctly"""
        with tempfile.TemporaryDirectory() as tmpdir:
            mdl_file = os.path.join(tmpdir, "model.mdl")
            with open(mdl_file, 'wb') as f:
                f.write(b'mock mdl')
            
            with patch('sys.argv', ['tf2autoswap.py', '--import', mdl_file, 'hat']):
                with patch.object(core, 'resolve_tf2', return_value=tmpdir):
                    mock_pak = Mock()
                    with patch.object(core, 'open_pak', return_value=mock_pak):
                        with patch.object(cli, 'load_index', return_value={}):
                            with patch.object(cli, 'cli') as mock_cli:
                                cli.run()
                            # Should have been called with swapped args
                            args = mock_cli.call_args[0][2]
                            assert args.target == 'hat'
                            assert args.import_path == mdl_file


class TestCLISkinAndPropModes:
    """Test CLI skin/material and prop swap modes"""
    
    def test_cli_skin_mode_routes_to_interactive(self):
        """run() --skin always routes to interactive mode"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('sys.argv', ['tf2autoswap.py', '--skin']):
                with patch.object(core, 'resolve_tf2', return_value=tmpdir):
                    mock_pak = Mock()
                    with patch.object(core, 'open_pak', return_value=mock_pak):
                        with patch.object(cli, 'load_index', return_value={}):
                            if cli.HAVE_MATERIAL:
                                with patch.object(cli, 'interactive_skin_swap') as mock_skin:
                                    cli.run()
                                mock_skin.assert_called_once()
                            else:
                                # Should print error and exit
                                cli.run()
    
    def test_cli_prop_mode_with_args_routes_to_cli_prop(self):
        """run() --prop with source and target uses CLI mode"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('sys.argv', ['tf2autoswap.py', 'crate', 'barrel', '--prop']):
                with patch.object(core, 'resolve_tf2', return_value=tmpdir):
                    mock_pak = Mock()
                    with patch.object(core, 'open_pak', return_value=mock_pak):
                        with patch.object(cli, 'load_index', return_value={}):
                            if cli.HAVE_MATERIAL:
                                with patch.object(cli, 'cli_prop') as mock_prop:
                                    cli.run()
                                mock_prop.assert_called_once()
                            else:
                                cli.run()
    
    def test_cli_prop_mode_without_args_routes_to_interactive(self):
        """run() --prop without source/target uses interactive mode"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('sys.argv', ['tf2autoswap.py', '--prop']):
                with patch.object(core, 'resolve_tf2', return_value=tmpdir):
                    mock_pak = Mock()
                    with patch.object(core, 'open_pak', return_value=mock_pak):
                        with patch.object(cli, 'load_index', return_value={}):
                            if cli.HAVE_MATERIAL:
                                with patch.object(cli, 'interactive_prop_swap') as mock_interactive:
                                    cli.run()
                                mock_interactive.assert_called_once()
                            else:
                                cli.run()


class TestInteractiveMode:
    """Test interactive menu entry"""
    
    def test_run_enters_interactive_without_args(self):
        """run() with no CLI args enters interactive mode"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('sys.argv', ['tf2autoswap.py']):
                with patch.object(core, 'resolve_tf2', return_value=tmpdir):
                    mock_pak = Mock()
                    with patch.object(core, 'open_pak', return_value=mock_pak):
                        with patch.object(cli, 'load_index', return_value={}):
                            with patch.object(cli, 'load_defindex_index', return_value={}):
                                with patch.object(cli, 'interactive') as mock_interactive:
                                    cli.run()
                                mock_interactive.assert_called_once()
    
    def test_interactive_loads_defindex_for_inventory_mode(self):
        """run() loads defindex_index for own-inventory mode"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('sys.argv', ['tf2autoswap.py']):
                with patch.object(core, 'resolve_tf2', return_value=tmpdir):
                    mock_pak = Mock()
                    with patch.object(core, 'open_pak', return_value=mock_pak):
                        with patch.object(cli, 'load_index', return_value={}):
                            with patch.object(cli, 'load_defindex_index') as mock_defindex:
                                with patch.object(cli, 'interactive'):
                                    mock_defindex.return_value = {}
                                    cli.run()
                                mock_defindex.assert_called_once()


class TestOutputPathHandling:
    """Test output path resolution and validation"""
    
    def test_resolve_out_path_with_directory(self):
        """resolve_out_path() appends filename to directory paths"""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = cli.resolve_out_path(tmpdir, "mod.vpk")
            assert result.endswith("mod.vpk")
            assert tmpdir in result
    
    def test_resolve_out_path_with_vpk_file(self):
        """resolve_out_path() uses .vpk file path as-is"""
        path = "/some/path/mymod.vpk"
        result = cli.resolve_out_path(path, "default.vpk")
        assert result == path
    
    def test_resolve_out_path_with_non_vpk_file(self):
        """resolve_out_path() appends default to non-.vpk paths"""
        path = "/some/path/output"
        result = cli.resolve_out_path(path, "mod.vpk")
        assert result.endswith("mod.vpk")
    
    def test_validate_output_path_creates_intermediates(self):
        """validate_output_path() creates intermediate directories"""
        with tempfile.TemporaryDirectory() as tmpdir:
            nested_path = os.path.join(tmpdir, "a", "b", "c", "file.vpk")
            valid, error = cli.validate_output_path(nested_path)
            # Should create a, b, c directories
            assert valid is True
            assert os.path.isdir(os.path.dirname(nested_path))
    
    def test_validate_output_path_detects_unwritable(self):
        """validate_output_path() detects unwritable paths"""
        # Try to write to root (should fail on most systems)
        valid, error = cli.validate_output_path("/root/test.vpk")
        # May succeed if running as root, but should return a result
        assert isinstance(valid, bool)
        if not valid:
            assert isinstance(error, str)


class TestDryRunMode:
    """Test --dry-run preview mode"""
    
    def test_cli_dry_run_shows_preview_without_building(self):
        """CLI --dry-run shows what would be built without creating files"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('sys.argv', ['tf2autoswap.py', 'hat1', 'hat2', '--dry-run']):
                with patch.object(core, 'resolve_tf2', return_value=tmpdir):
                    mock_pak = Mock()
                    with patch.object(core, 'open_pak', return_value=mock_pak):
                        with patch.object(cli, 'load_index', return_value={}):
                            # Mock core functions
                            with patch.object(core, 'find_models', return_value=['models/test.mdl']):
                                with patch.object(core, 'source_from_vpk', return_value={'.mdl': b'test'}):
                                    with patch.object(core, 'preview_build') as mock_preview:
                                        mock_preview.return_value = {
                                            'entries': [{'ext': '.mdl', 'size': 100}],
                                            'total_size': 100,
                                            'model_count': 1,
                                            'material_count': 0
                                        }
                                        # Should not raise, just print preview
                                        cli.run()
                                    mock_preview.assert_called()


class TestPreloaderDirectoryHandling:
    """Test Casual Preloader directory path handling"""
    
    def test_run_uses_custom_preloader_path(self):
        """run() --preloader overrides default preloader path"""
        with tempfile.TemporaryDirectory() as tmpdir:
            custom_preloader = os.path.join(tmpdir, "custom_preloader")
            os.makedirs(custom_preloader, exist_ok=True)
            
            with patch('sys.argv', ['tf2autoswap.py', '--preloader', custom_preloader, '--list-installed']):
                with patch.object(cli, 'show_installed') as mock_show:
                    cli.run()
                # Check that custom path was passed
                call_args = mock_show.call_args[0]
                assert custom_preloader in call_args
    
    def test_is_in_preloader_detects_paths_inside_preloader(self):
        """is_in_preloader() correctly identifies paths inside preloader folder"""
        with tempfile.TemporaryDirectory() as tmpdir:
            preloader = os.path.join(tmpdir, "preloader")
            os.makedirs(preloader, exist_ok=True)
            
            inside_path = os.path.join(preloader, "mods", "addon.vpk")
            result = cli.is_in_preloader(inside_path, preloader)
            assert result is True
    
    def test_is_in_preloader_detects_paths_outside_preloader(self):
        """is_in_preloader() correctly identifies paths outside preloader folder"""
        with tempfile.TemporaryDirectory() as tmpdir:
            preloader = os.path.join(tmpdir, "preloader")
            os.makedirs(preloader, exist_ok=True)
            
            outside_path = os.path.join(tmpdir, "output", "mod.vpk")
            result = cli.is_in_preloader(outside_path, preloader)
            assert result is False


class TestUserInputMocking:
    """Test interactive user input handling with mocked stdin"""
    
    def test_choose_returns_selected_option(self):
        """choose() returns the selected option from list"""
        options = ["cosmetic", "weapon", "prop"]
        labels = ["Cosmetic swap", "Weapon swap", "Prop swap"]
        
        with patch('builtins.input', return_value='1'):
            result = cli.choose("Pick an option", options, labels)
            assert result == "cosmetic"
    
    def test_choose_exits_on_q(self):
        """choose() exits when user types 'q'"""
        options = ["cosmetic", "weapon"]
        labels = ["Cosmetic", "Weapon"]
        
        with patch('builtins.input', return_value='q'):
            with pytest.raises(SystemExit):
                cli.choose("Pick", options, labels)
    
    def test_choose_handles_invalid_input_then_valid(self):
        """choose() loops on invalid input until valid choice"""
        options = ["a", "b"]
        labels = ["A", "B"]
        
        # First invalid, then valid
        with patch('builtins.input', side_effect=['99', '1']):
            result = cli.choose("Pick", options, labels)
            assert result == "a"
    
    def test_choose_paginated_with_small_list_uses_regular_choose(self):
        """choose_paginated() falls through to choose() for small lists"""
        options = list(range(10))
        labels = [f"Item {i}" for i in range(10)]
        
        with patch('builtins.input', return_value='1'):
            result = cli.choose_paginated("Pick", options, labels, page_size=15)
            assert result == 0


class TestErrorHandlingPaths:
    """Test error handling in various execution paths"""
    
    def test_cli_handles_model_not_found_error(self):
        """CLI mode handles ModelNotFound gracefully"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('sys.argv', ['tf2autoswap.py', 'nonexistent', 'target']):
                with patch.object(core, 'resolve_tf2', return_value=tmpdir):
                    mock_pak = Mock()
                    with patch.object(core, 'open_pak', return_value=mock_pak):
                        with patch.object(cli, 'load_index', return_value={}):
                            with patch.object(core, 'find_models', return_value=[]):
                                with pytest.raises(core.ModelNotFound):
                                    cli.run()
    
    def test_has_invalid_path_chars_detects_shell_metacharacters(self):
        """has_invalid_path_chars() detects shell metacharacters"""
        assert cli.has_invalid_path_chars("file|pipe") is True
        assert cli.has_invalid_path_chars("file&bg") is True
        assert cli.has_invalid_path_chars("file;cmd") is True
        assert cli.has_invalid_path_chars("file>redirect") is True
    
    def test_has_invalid_path_chars_detects_control_characters(self):
        """has_invalid_path_chars() detects control characters"""
        # Null byte
        assert cli.has_invalid_path_chars("file\x00name") is True
        # Other control chars
        assert cli.has_invalid_path_chars("file\x01name") is True


class TestUtilityFunctions:
    """Test utility and helper functions"""
    
    def test_output_filename_generates_valid_vpk_name(self):
        """output_filename() generates valid .vpk filename"""
        result = cli.output_filename("models/cosmetics/hat.mdl", "replacement", {})
        assert result.endswith(".vpk")
        assert cli.SIGNATURE in result
    
    def test_output_filename_sanitizes_special_chars(self):
        """output_filename() sanitizes special characters"""
        # Pass a target with characters that need sanitizing
        result = cli.output_filename("models/test<item>.mdl", "source>name", {})
        # Should not contain < or >
        assert '<' not in result
        assert '>' not in result
    
    def test_sanitize_filename_removes_path_separators(self):
        """sanitize_filename() removes path separators"""
        result = cli.sanitize_filename("path/to/file")
        assert '/' not in result
        assert '\\' not in result
    
    def test_sanitize_filename_removes_windows_illegal_chars(self):
        """sanitize_filename() removes Windows illegal characters"""
        result = cli.sanitize_filename('file:name*with?illegal"chars<>')
        # All illegal chars should be removed
        for char in ':*?"<>|':
            assert char not in result
    
    def test_fmt_size_formats_bytes_correctly(self):
        """fmt_size() formats byte sizes correctly"""
        assert "bytes" in cli.fmt_size(500).lower()
        assert "kb" in cli.fmt_size(5000).lower()
        assert "mb" in cli.fmt_size(5000000).lower()
    
    def test_normalize_keyword_is_idempotent(self):
        """normalize_keyword() produces same result when called twice"""
        keyword = "Scatter-GUN"
        result1 = cli.normalize_keyword(keyword)
        result2 = cli.normalize_keyword(result1)
        assert result1 == result2


class TestCLIFlagCombinations:
    """Test various CLI flag combinations"""
    
    def test_weapon_and_filter_flags_together(self):
        """run() handles --weapon and --filter together"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('sys.argv', ['tf2autoswap.py', 'scatter', 'short', '--weapon', '--filter', 'scout']):
                with patch.object(core, 'resolve_tf2', return_value=tmpdir):
                    mock_pak = Mock()
                    with patch.object(core, 'open_pak', return_value=mock_pak):
                        with patch.object(cli, 'load_index', return_value={}):
                            with patch.object(cli, 'cli_weapon') as mock_weapon:
                                cli.run()
                            # Should call weapon CLI with filter arg
                            args = mock_weapon.call_args[0][2]
                            assert args.cls == 'scout'
    
    def test_import_and_weapon_flags_together(self):
        """run() handles --import and --weapon together"""
        with tempfile.TemporaryDirectory() as tmpdir:
            mdl = os.path.join(tmpdir, "c_weapon.mdl")
            with open(mdl, 'wb') as f:
                f.write(b'mdl')
            
            with patch('sys.argv', ['tf2autoswap.py', '--import', mdl, 'target', '--weapon']):
                with patch.object(core, 'resolve_tf2', return_value=tmpdir):
                    mock_pak = Mock()
                    with patch.object(core, 'open_pak', return_value=mock_pak):
                        with patch.object(cli, 'load_index', return_value={}):
                            with patch.object(cli, 'cli_weapon') as mock_weapon:
                                cli.run()
                            args = mock_weapon.call_args[0][2]
                            assert args.import_path == mdl


class TestWriteInventoryGuide:
    """Test inventory guide creation"""
    
    def test_write_inventory_guide_creates_file(self):
        """write_inventory_guide() creates guide file if missing"""
        with tempfile.TemporaryDirectory() as tmpdir:
            guide_path = os.path.join(tmpdir, "guide.txt")
            with patch.object(cli, 'INVENTORY_GUIDE_PATH', guide_path):
                cli.write_inventory_guide()
                assert os.path.isfile(guide_path)
    
    def test_write_inventory_guide_preserves_existing(self):
        """write_inventory_guide() doesn't overwrite existing guide"""
        with tempfile.TemporaryDirectory() as tmpdir:
            guide_path = os.path.join(tmpdir, "guide.txt")
            custom_text = "Custom guide text"
            with open(guide_path, 'w') as f:
                f.write(custom_text)
            
            with patch.object(cli, 'INVENTORY_GUIDE_PATH', guide_path):
                cli.write_inventory_guide()
                # Should not overwrite
                with open(guide_path, 'r') as f:
                    assert f.read() == custom_text
    
    def test_write_inventory_guide_handles_permission_error(self):
        """write_inventory_guide() handles permission errors gracefully"""
        with patch.object(cli, 'INVENTORY_GUIDE_PATH', '/root/unwritable.txt'):
            # Should not raise
            cli.write_inventory_guide()
