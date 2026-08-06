#!/usr/bin/env python3
"""
test_tf2autoswap_menus.py - Tests for interactive menu selection functions in tf2autoswap.py

Tests the interactive menu functions using terminal mocking with io.StringIO and unittest.mock:
- choose() - single-choice menu selection
- choose_paginated() - paginated menu for large lists
- search_and_pick() - search archive and select model

Uses unittest.mock.patch() to mock sys.stdin/sys.stdout and simulate user input.
Tests cover valid selections, invalid input handling, pagination logic, and edge cases.

Author: Melancholy Sky
Co-author: AI assistance via OpenRouter
"""

import pytest
import sys
import io
from unittest.mock import patch, MagicMock
import tf2autoswap as cli


class TestChooseBasic:
    """Test choose() function with basic menu selection"""

    def test_choose_first_option(self):
        """choose() returns first option when user selects 1"""
        options = ['option_a', 'option_b', 'option_c']
        labels = ['Option A', 'Option B', 'Option C']
        
        with patch('sys.stdin', io.StringIO('1\n')):
            with patch('sys.stdout', io.StringIO()):
                result = cli.choose('Select', options, labels)
        
        assert result == 'option_a'

    def test_choose_middle_option(self):
        """choose() returns middle option when user selects mid-range number"""
        options = ['option_a', 'option_b', 'option_c', 'option_d', 'option_e']
        labels = ['A', 'B', 'C', 'D', 'E']
        
        with patch('sys.stdin', io.StringIO('3\n')):
            with patch('sys.stdout', io.StringIO()):
                result = cli.choose('Select', options, labels)
        
        assert result == 'option_c'

    def test_choose_last_option(self):
        """choose() returns last option when user selects max number"""
        options = ['option_a', 'option_b', 'option_c']
        labels = ['Option A', 'Option B', 'Option C']
        
        with patch('sys.stdin', io.StringIO('3\n')):
            with patch('sys.stdout', io.StringIO()):
                result = cli.choose('Select', options, labels)
        
        assert result == 'option_c'

    def test_choose_single_option(self):
        """choose() works with a single option"""
        options = ['only_option']
        labels = ['Only Option']
        
        with patch('sys.stdin', io.StringIO('1\n')):
            with patch('sys.stdout', io.StringIO()):
                result = cli.choose('Select', options, labels)
        
        assert result == 'only_option'

    def test_choose_quit_exits(self):
        """choose() exits when user enters 'q'"""
        options = ['option_a', 'option_b']
        labels = ['A', 'B']
        
        with patch('sys.stdin', io.StringIO('q\n')):
            with patch('sys.stdout', io.StringIO()):
                with pytest.raises(SystemExit):
                    cli.choose('Select', options, labels)

    def test_choose_quit_case_insensitive(self):
        """choose() exits when user enters 'Q' (uppercase)"""
        options = ['option_a', 'option_b']
        labels = ['A', 'B']
        
        with patch('sys.stdin', io.StringIO('Q\n')):
            with patch('sys.stdout', io.StringIO()):
                with pytest.raises(SystemExit):
                    cli.choose('Select', options, labels)


class TestChooseInvalidInput:
    """Test choose() function with invalid input handling"""

    def test_choose_invalid_then_valid(self):
        """choose() re-prompts after invalid input, then accepts valid"""
        options = ['option_a', 'option_b', 'option_c']
        labels = ['A', 'B', 'C']
        
        # First invalid (0), then valid (2)
        with patch('sys.stdin', io.StringIO('0\n2\n')):
            with patch('sys.stdout', io.StringIO()):
                result = cli.choose('Select', options, labels)
        
        assert result == 'option_b'

    def test_choose_out_of_range_then_valid(self):
        """choose() re-prompts when selection is out of range"""
        options = ['option_a', 'option_b', 'option_c']
        labels = ['A', 'B', 'C']
        
        # First 99 (out of range), then valid 1
        with patch('sys.stdin', io.StringIO('99\n1\n')):
            with patch('sys.stdout', io.StringIO()):
                result = cli.choose('Select', options, labels)
        
        assert result == 'option_a'

    def test_choose_negative_number_then_valid(self):
        """choose() re-prompts when given negative number"""
        options = ['option_a', 'option_b']
        labels = ['A', 'B']
        
        # First -1, then valid 2
        with patch('sys.stdin', io.StringIO('-1\n2\n')):
            with patch('sys.stdout', io.StringIO()):
                result = cli.choose('Select', options, labels)
        
        assert result == 'option_b'

    def test_choose_non_numeric_then_valid(self):
        """choose() re-prompts when given non-numeric input"""
        options = ['option_a', 'option_b', 'option_c']
        labels = ['A', 'B', 'C']
        
        # First 'abc', then valid 2
        with patch('sys.stdin', io.StringIO('abc\n2\n')):
            with patch('sys.stdout', io.StringIO()):
                result = cli.choose('Select', options, labels)
        
        assert result == 'option_b'

    def test_choose_empty_input_then_valid(self):
        """choose() re-prompts when given empty input"""
        options = ['option_a', 'option_b']
        labels = ['A', 'B']
        
        # First empty line, then valid 1
        with patch('sys.stdin', io.StringIO('\n1\n')):
            with patch('sys.stdout', io.StringIO()):
                result = cli.choose('Select', options, labels)
        
        assert result == 'option_a'


class TestChoosePaginatedBasic:
    """Test choose_paginated() function with pagination logic"""

    def test_choose_paginated_small_list_delegates_to_choose(self):
        """choose_paginated() delegates to choose() when list fits in one page"""
        options = ['opt_a', 'opt_b', 'opt_c']
        labels = ['A', 'B', 'C']
        
        with patch('sys.stdin', io.StringIO('2\n')):
            with patch('sys.stdout', io.StringIO()):
                result = cli.choose_paginated('Select', options, labels, page_size=15)
        
        assert result == 'opt_b'

    def test_choose_paginated_first_page_selection(self):
        """choose_paginated() selects item from first page"""
        options = [f'opt_{i}' for i in range(30)]
        labels = [f'Option {i}' for i in range(30)]
        
        # Select item 5 on first page
        with patch('sys.stdin', io.StringIO('5\n')):
            with patch('sys.stdout', io.StringIO()):
                result = cli.choose_paginated('Select', options, labels, page_size=15)
        
        assert result == 'opt_4'

    def test_choose_paginated_next_page_then_select(self):
        """choose_paginated() navigates to next page and selects"""
        options = [f'opt_{i}' for i in range(30)]
        labels = [f'Option {i}' for i in range(30)]
        
        # Press 'n' for next page, then select item 20
        with patch('sys.stdin', io.StringIO('n\n20\n')):
            with patch('sys.stdout', io.StringIO()):
                result = cli.choose_paginated('Select', options, labels, page_size=15)
        
        assert result == 'opt_19'

    def test_choose_paginated_prev_page_navigation(self):
        """choose_paginated() navigates to next page, then back with 'p'"""
        options = [f'opt_{i}' for i in range(30)]
        labels = [f'Option {i}' for i in range(30)]
        
        # Next page, previous page, then select item 5
        with patch('sys.stdin', io.StringIO('n\np\n5\n')):
            with patch('sys.stdout', io.StringIO()):
                result = cli.choose_paginated('Select', options, labels, page_size=15)
        
        assert result == 'opt_4'

    def test_choose_paginated_direct_selection_from_second_page(self):
        """choose_paginated() selects item directly by number from any page"""
        options = [f'opt_{i}' for i in range(30)]
        labels = [f'Option {i}' for i in range(30)]
        
        # Directly select item 25 (on second page) without navigating
        with patch('sys.stdin', io.StringIO('25\n')):
            with patch('sys.stdout', io.StringIO()):
                result = cli.choose_paginated('Select', options, labels, page_size=15)
        
        assert result == 'opt_24'

    def test_choose_paginated_quit_from_paginated_list(self):
        """choose_paginated() exits when user enters 'q'"""
        options = [f'opt_{i}' for i in range(30)]
        labels = [f'Option {i}' for i in range(30)]
        
        with patch('sys.stdin', io.StringIO('q\n')):
            with patch('sys.stdout', io.StringIO()):
                with pytest.raises(SystemExit):
                    cli.choose_paginated('Select', options, labels, page_size=15)


class TestChoosePaginatedEdgeCases:
    """Test choose_paginated() edge cases and boundary conditions"""

    def test_choose_paginated_exactly_one_page(self):
        """choose_paginated() handles list exactly equal to page_size"""
        options = [f'opt_{i}' for i in range(15)]
        labels = [f'Option {i}' for i in range(15)]
        
        with patch('sys.stdin', io.StringIO('10\n')):
            with patch('sys.stdout', io.StringIO()):
                result = cli.choose_paginated('Select', options, labels, page_size=15)
        
        assert result == 'opt_9'

    def test_choose_paginated_one_more_than_page_size(self):
        """choose_paginated() handles list with exactly page_size + 1 items"""
        options = [f'opt_{i}' for i in range(16)]
        labels = [f'Option {i}' for i in range(16)]
        
        # Select last item (on second page)
        with patch('sys.stdin', io.StringIO('16\n')):
            with patch('sys.stdout', io.StringIO()):
                result = cli.choose_paginated('Select', options, labels, page_size=15)
        
        assert result == 'opt_15'

    def test_choose_paginated_invalid_navigation_on_first_page(self):
        """choose_paginated() ignores 'p' when on first page"""
        options = [f'opt_{i}' for i in range(30)]
        labels = [f'Option {i}' for i in range(30)]
        
        # Try 'p' on first page, then valid selection
        with patch('sys.stdin', io.StringIO('p\n5\n')):
            with patch('sys.stdout', io.StringIO()):
                result = cli.choose_paginated('Select', options, labels, page_size=15)
        
        assert result == 'opt_4'

    def test_choose_paginated_invalid_navigation_on_last_page(self):
        """choose_paginated() ignores 'n' when on last page"""
        options = [f'opt_{i}' for i in range(30)]
        labels = [f'Option {i}' for i in range(30)]
        
        # Navigate to last page, try 'n', then select
        with patch('sys.stdin', io.StringIO('n\nn\n20\n')):
            with patch('sys.stdout', io.StringIO()):
                result = cli.choose_paginated('Select', options, labels, page_size=15)
        
        assert result == 'opt_19'

    def test_choose_paginated_large_list(self):
        """choose_paginated() handles very large lists with multiple pages"""
        options = [f'opt_{i}' for i in range(100)]
        labels = [f'Option {i}' for i in range(100)]
        
        # Select item 75 directly
        with patch('sys.stdin', io.StringIO('75\n')):
            with patch('sys.stdout', io.StringIO()):
                result = cli.choose_paginated('Select', options, labels, page_size=15)
        
        assert result == 'opt_74'


class TestSearchAndPickBasic:
    """Test search_and_pick() function with mock VPK archive"""

    def test_search_and_pick_single_result_auto_selects(self):
        """search_and_pick() auto-selects when exactly one match is found"""
        mock_pak = MagicMock()
        
        # Mock core.all_stems to return list for typo suggestions
        with patch('tf2autoswap.core.all_stems', return_value=['hat', 'helmet', 'headband']):
            # Mock core.find_models to return single result
            with patch('tf2autoswap.core.find_models', return_value=['models/cosmetics/unique_hat.mdl']):
                with patch('sys.stdin', io.StringIO('unique\n')):
                    with patch('sys.stdout', io.StringIO()):
                        result = cli.search_and_pick(mock_pak, 'cosmetic', None, {})
        
        assert result == 'models/cosmetics/unique_hat.mdl'

    def test_search_and_pick_multiple_results_requires_selection(self):
        """search_and_pick() shows menu when multiple matches are found"""
        mock_pak = MagicMock()
        
        with patch('tf2autoswap.core.all_stems', return_value=['hat', 'helmet', 'headband']):
            # Return multiple results
            with patch('tf2autoswap.core.find_models', return_value=[
                'models/cosmetics/hat_a.mdl',
                'models/cosmetics/hat_b.mdl',
                'models/cosmetics/hat_c.mdl'
            ]):
                # Search 'hat', then select option 2
                with patch('sys.stdin', io.StringIO('hat\n2\n')):
                    with patch('sys.stdout', io.StringIO()):
                        result = cli.search_and_pick(mock_pak, 'cosmetic', None, {})
        
        assert result == 'models/cosmetics/hat_b.mdl'

    def test_search_and_pick_no_results_shows_suggestions(self):
        """search_and_pick() shows typo suggestions when no matches found"""
        mock_pak = MagicMock()
        
        with patch('tf2autoswap.core.all_stems', return_value=['hat', 'helmet', 'headband']):
            # First search returns nothing, second returns result
            with patch('tf2autoswap.core.find_models', side_effect=[
                [],  # First search: no results
                ['models/cosmetics/hat.mdl']  # Second search: found
            ]):
                # Search 'ht' (no results), then 'hat' (found)
                with patch('sys.stdin', io.StringIO('ht\nhat\n')):
                    with patch('sys.stdout', io.StringIO()):
                        result = cli.search_and_pick(mock_pak, 'cosmetic', None, {})
        
        assert result == 'models/cosmetics/hat.mdl'

    def test_search_and_pick_quit_during_search(self):
        """search_and_pick() exits when user enters 'q'"""
        mock_pak = MagicMock()
        
        with patch('tf2autoswap.core.all_stems', return_value=['hat']):
            with patch('sys.stdin', io.StringIO('q\n')):
                with patch('sys.stdout', io.StringIO()):
                    with pytest.raises(SystemExit):
                        cli.search_and_pick(mock_pak, 'cosmetic', None, {})

    def test_search_and_pick_empty_keyword_reprompts(self):
        """search_and_pick() re-prompts when user enters empty keyword"""
        mock_pak = MagicMock()
        
        with patch('tf2autoswap.core.all_stems', return_value=['hat']):
            with patch('tf2autoswap.core.find_models', return_value=['models/cosmetics/hat.mdl']):
                # First empty, then valid keyword
                with patch('sys.stdin', io.StringIO('\nhat\n')):
                    with patch('sys.stdout', io.StringIO()):
                        result = cli.search_and_pick(mock_pak, 'cosmetic', None, {})
        
        assert result == 'models/cosmetics/hat.mdl'


class TestSearchAndPickWithSchema:
    """Test search_and_pick() with schema-based name lookup"""

    def test_search_and_pick_friendly_name_fallback(self):
        """search_and_pick() searches friendly names when archive path search fails"""
        mock_pak = MagicMock()
        mock_index = {
            'models/cosmetics/special_hat': MagicMock(name='Special Hat', item_type='cosmetic')
        }
        
        with patch('tf2autoswap.core.all_stems', return_value=['special_hat']):
            # First find_models returns nothing, second returns result after name lookup
            with patch('tf2autoswap.core.find_models', side_effect=[
                [],  # Archive path search: no results
                ['models/cosmetics/special_hat.mdl']  # After friendly name lookup
            ]):
                # Mock reverse_name_lookup to return stem for friendly name search
                with patch('tf2autoswap.reverse_name_lookup', return_value=['special_hat']):
                    with patch('sys.stdin', io.StringIO('Special Hat\n')):
                        with patch('sys.stdout', io.StringIO()):
                            result = cli.search_and_pick(mock_pak, 'cosmetic', None, mock_index)
        
        assert result == 'models/cosmetics/special_hat.mdl'

    def test_search_and_pick_with_class_filter(self):
        """search_and_pick() passes class filter to core.find_models"""
        mock_pak = MagicMock()
        
        with patch('tf2autoswap.core.all_stems', return_value=['hat']):
            with patch('tf2autoswap.core.find_models', return_value=['models/cosmetics/scout_hat.mdl']) as mock_find:
                with patch('sys.stdin', io.StringIO('hat\n')):
                    with patch('sys.stdout', io.StringIO()):
                        result = cli.search_and_pick(mock_pak, 'cosmetic', 'scout', {})
        
        # Verify class filter was passed
        mock_find.assert_called_once()
        assert mock_find.call_args[0][2] == 'scout'
        assert result == 'models/cosmetics/scout_hat.mdl'


class TestSearchAndPickEmptyResults:
    """Test search_and_pick() handling of empty option lists"""

    def test_search_and_pick_persistent_no_results(self):
        """search_and_pick() continues prompting when searches keep failing"""
        mock_pak = MagicMock()
        
        with patch('tf2autoswap.core.all_stems', return_value=['hat', 'helmet']):
            # Three failed searches, then success
            with patch('tf2autoswap.core.find_models', side_effect=[
                [],  # First search: fail
                [],  # Second search: fail
                [],  # Third search: fail
                ['models/cosmetics/hat.mdl']  # Fourth: success
            ]):
                with patch('sys.stdin', io.StringIO('xyz\nabc\ndef\nhat\n')):
                    with patch('sys.stdout', io.StringIO()):
                        result = cli.search_and_pick(mock_pak, 'cosmetic', None, {})
        
        assert result == 'models/cosmetics/hat.mdl'

    def test_search_and_pick_no_schema_fallback(self):
        """search_and_pick() works without schema (no friendly name search)"""
        mock_pak = MagicMock()
        
        # Test with HAVE_SCHEMA=False scenario (index=None)
        with patch('tf2autoswap.core.all_stems', return_value=['hat']):
            with patch('tf2autoswap.core.find_models', return_value=['models/cosmetics/hat.mdl']):
                with patch('sys.stdin', io.StringIO('hat\n')):
                    with patch('sys.stdout', io.StringIO()):
                        result = cli.search_and_pick(mock_pak, 'cosmetic', None, None)
        
        assert result == 'models/cosmetics/hat.mdl'
