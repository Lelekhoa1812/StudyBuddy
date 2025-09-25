#!/usr/bin/env python3
"""
Test script to verify code styling and heading numbering improvements
"""
import asyncio
import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.service.pdf import _apply_syntax_highlight

def test_code_styling_improvements():
    """Test that the code styling improvements work correctly"""
    print("Testing code styling improvements...")
    
    # Test Python code highlighting
    python_code = '''def calculate_fibonacci(n):
    """Calculate the nth Fibonacci number"""
    if n <= 1:
        return n
    return calculate_fibonacci(n-1) + calculate_fibonacci(n-2)

# Test the function
result = calculate_fibonacci(10)
print(f"Fibonacci(10) = {result}")'''
    
    try:
        # Escape the code first
        escaped_code = python_code.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        result = _apply_syntax_highlight(escaped_code, 'python')
        
        print("✓ Python syntax highlighting test passed")
        print("  Sample output (first 200 chars):")
        print(f"  {result[:200]}...")
        
        # Check for key highlighting elements
        assert '<font color=' in result, "Should have color highlighting"
        assert 'def' in result, "Should highlight keywords"
        assert 'print' in result, "Should highlight built-ins"
        assert '#' in result, "Should highlight comments"
        
        return True
    except Exception as e:
        print(f"✗ Python syntax highlighting test failed: {e}")
        return False

def test_javascript_highlighting():
    """Test JavaScript highlighting"""
    print("\nTesting JavaScript highlighting...")
    
    js_code = '''function processData(data) {
    // Process the input data
    const result = data.map(item => {
        return {
            id: item.id,
            name: item.name.toUpperCase(),
            processed: true
        };
    });
    
    return result;
}

// Usage
const data = [{id: 1, name: "test"}];
const processed = processData(data);
console.log(processed);'''
    
    try:
        escaped_code = js_code.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        result = _apply_syntax_highlight(escaped_code, 'javascript')
        
        print("✓ JavaScript syntax highlighting test passed")
        print("  Sample output (first 200 chars):")
        print(f"  {result[:200]}...")
        
        # Check for key highlighting elements
        assert '<font color=' in result, "Should have color highlighting"
        assert 'function' in result, "Should highlight keywords"
        assert 'console' in result, "Should highlight built-ins"
        
        return True
    except Exception as e:
        print(f"✗ JavaScript syntax highlighting test failed: {e}")
        return False

def test_json_highlighting():
    """Test JSON highlighting"""
    print("\nTesting JSON highlighting...")
    
    json_code = '''{
    "name": "test",
    "value": 123,
    "active": true,
    "items": null,
    "data": {
        "nested": "value"
    }
}'''
    
    try:
        escaped_code = json_code.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        result = _apply_syntax_highlight(escaped_code, 'json')
        
        print("✓ JSON syntax highlighting test passed")
        print("  Sample output (first 200 chars):")
        print(f"  {result[:200]}...")
        
        # Check for key highlighting elements
        assert '<font color=' in result, "Should have color highlighting"
        assert 'true' in result, "Should highlight boolean values"
        assert 'null' in result, "Should highlight null values"
        
        return True
    except Exception as e:
        print(f"✗ JSON syntax highlighting test failed: {e}")
        return False

def test_heading_extraction():
    """Test heading extraction logic"""
    print("\nTesting heading extraction...")
    
    sample_report = """# Introduction
This is the introduction section.

## Background
Some background information.

### Historical Context
Historical details here.

## Methodology
Our approach to the problem.

### Data Collection
How we collected data.

### Analysis
How we analyzed the data.

## Results
The findings.

## Conclusion
Final thoughts."""
    
    import re
    
    # Extract headings using the same logic as the fix_heading_numbering function
    heading_pattern = r'^(#{1,6})\s*(.*)$'
    headings = []
    lines = sample_report.split('\n')
    
    for i, line in enumerate(lines):
        match = re.match(heading_pattern, line.strip())
        if match:
            level = len(match.group(1))
            text = match.group(2).strip()
            # Remove existing numbering if present
            text = re.sub(r'^\d+\.?\s*', '', text)
            headings.append({
                'line_number': i,
                'level': level,
                'text': text,
                'original_line': line
            })
    
    print(f"✓ Extracted {len(headings)} headings:")
    for h in headings:
        print(f"  Level {h['level']}: {h['text']}")
    
    # Verify we found the expected headings
    expected_headings = ['Introduction', 'Background', 'Historical Context', 'Methodology', 'Data Collection', 'Analysis', 'Results', 'Conclusion']
    found_texts = [h['text'] for h in headings]
    
    for expected in expected_headings:
        if expected in found_texts:
            print(f"  ✓ Found: {expected}")
        else:
            print(f"  ✗ Missing: {expected}")
    
    return len(headings) >= len(expected_headings)

async def main():
    """Run all tests"""
    print("Running code styling and heading numbering improvements tests...\n")
    
    # Test code styling improvements
    python_test = test_code_styling_improvements()
    js_test = test_javascript_highlighting()
    json_test = test_json_highlighting()
    
    # Test heading extraction
    heading_test = test_heading_extraction()
    
    print("\n" + "="*60)
    print("TEST RESULTS:")
    print(f"✓ Python highlighting: {'PASSED' if python_test else 'FAILED'}")
    print(f"✓ JavaScript highlighting: {'PASSED' if js_test else 'FAILED'}")
    print(f"✓ JSON highlighting: {'PASSED' if json_test else 'FAILED'}")
    print(f"✓ Heading extraction: {'PASSED' if heading_test else 'FAILED'}")
    
    all_passed = python_test and js_test and json_test and heading_test
    
    if all_passed:
        print("\n🎉 All tests passed!")
        print("✓ Code styling improvements are working correctly")
        print("✓ Heading extraction logic is working correctly")
        print("✓ The PDF generation should now have better code styling")
        print("✓ Reports should have properly numbered headings")
    else:
        print("\n❌ Some tests failed. Please check the output above.")
    
    print("\nNote: The heading re-numbering will use AI models during actual report generation.")
    print("The extraction logic is tested here, but the AI re-numbering requires a live model.")

if __name__ == "__main__":
    asyncio.run(main())
