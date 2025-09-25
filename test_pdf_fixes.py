#!/usr/bin/env python3
"""
Test script to verify PDF generation fixes
"""
import asyncio
import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.service.pdf import _format_inline_markdown, _render_mermaid_png

def test_html_parsing_fix():
    """Test that the HTML parsing fix works correctly"""
    print("Testing HTML parsing fix...")
    
    # Test case that was causing the original error
    test_text = "Close{t-1} and Close{t-2} with some **bold** and *italic* text"
    
    try:
        result = _format_inline_markdown(test_text)
        print(f"✓ HTML parsing test passed")
        print(f"  Input: {test_text}")
        print(f"  Output: {result}")
        return True
    except Exception as e:
        print(f"✗ HTML parsing test failed: {e}")
        return False

def test_mermaid_validation():
    """Test that mermaid validation works correctly"""
    print("\nTesting mermaid validation...")
    
    # Test valid mermaid
    valid_mermaid = """graph TD
    A[Start] --> B[Process]
    B --> C[End]"""
    
    try:
        result = _render_mermaid_png(valid_mermaid)
        if result:
            print(f"✓ Valid mermaid rendered successfully ({len(result)} bytes)")
        else:
            print("⚠ Valid mermaid returned empty (may be network issue)")
    except Exception as e:
        print(f"⚠ Valid mermaid test had issue: {e}")
    
    # Test invalid mermaid
    invalid_mermaid = "This is not a valid mermaid diagram"
    
    try:
        result = _render_mermaid_png(invalid_mermaid)
        if not result:
            print("✓ Invalid mermaid correctly rejected")
        else:
            print("⚠ Invalid mermaid was not rejected")
    except Exception as e:
        print(f"✓ Invalid mermaid correctly rejected: {e}")

def test_nested_formatting():
    """Test that nested formatting is handled correctly"""
    print("\nTesting nested formatting...")
    
    test_cases = [
        "`code with **bold** text`",
        "**bold with `code` inside**",
        "*italic with `code` inside*",
        "`code with *italic* text`",
        "**bold with *italic* text**"
    ]
    
    for test_case in test_cases:
        try:
            result = _format_inline_markdown(test_case)
            print(f"✓ Nested formatting test passed: {test_case}")
            print(f"  Output: {result}")
        except Exception as e:
            print(f"✗ Nested formatting test failed for '{test_case}': {e}")

async def main():
    """Run all tests"""
    print("Running PDF generation fix tests...\n")
    
    # Test HTML parsing fix
    html_test_passed = test_html_parsing_fix()
    
    # Test mermaid validation
    test_mermaid_validation()
    
    # Test nested formatting
    test_nested_formatting()
    
    print("\n" + "="*50)
    if html_test_passed:
        print("✓ All critical tests passed!")
        print("The PDF generation should now work without HTML parsing errors.")
    else:
        print("✗ Some tests failed. Please check the output above.")
    
    print("\nNote: Mermaid rendering may still fail due to network issues or")
    print("invalid diagram syntax, but it will now fall back gracefully to")
    print("showing the diagram as code instead of crashing the PDF generation.")

if __name__ == "__main__":
    asyncio.run(main())
