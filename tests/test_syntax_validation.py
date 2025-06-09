"""
Syntax validation tests for all Python files
"""
import os
import sys
import py_compile
import ast


def test_file_syntax(file_path):
    """Test syntax of a Python file"""
    try:
        # Try compiling the file
        py_compile.compile(file_path, doraise=True)
        
        # Try parsing the AST
        with open(file_path, 'r') as f:
            source = f.read()
        ast.parse(source)
        
        return True, None
    except Exception as e:
        return False, str(e)


def test_all_syntax():
    """Test syntax of all relevant Python files"""
    print("=" * 50)
    print("SYNTAX VALIDATION TESTS")
    print("=" * 50)
    
    # Get the project root directory
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # Files to check
    files_to_check = [
        # Main files
        "discordbot.py",
        "generic_chat.py",
        "embed_utils.py",
        "user_quotas.py",
        
        # Cogs
        "cogs/ai_commands.py",
        "cogs/api_utils.py",
        "cogs/ddg_search.py",
        "cogs/fun_prompt.py",
        "cogs/image_gen.py",
        "cogs/model_management.py",
        "cogs/quota_management.py",
        "cogs/reminders.py",
        "cogs/tool_calling.py",
        
        # Tools
        "cogs/tools/__init__.py",
        "cogs/tools/base_tool.py",
        "cogs/tools/tool_registry.py",
        "cogs/tools/web_search_tool.py",
        "cogs/tools/content_tool.py",
    ]
    
    passed = 0
    failed = 0
    
    for file_path in files_to_check:
        full_path = os.path.join(project_root, file_path)
        
        if not os.path.exists(full_path):
            print(f"⚠️  {file_path:<40} FILE NOT FOUND")
            continue
        
        success, error = test_file_syntax(full_path)
        
        if success:
            print(f"✅ {file_path:<40} SYNTAX OK")
            passed += 1
        else:
            print(f"❌ {file_path:<40} SYNTAX ERROR")
            print(f"   Error: {error}")
            failed += 1
    
    print("\n" + "=" * 50)
    print(f"SYNTAX VALIDATION SUMMARY")
    print("=" * 50)
    print(f"Total files checked: {passed + failed}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    
    if failed == 0:
        print("\n🎉 All files have valid syntax!")
        return True
    else:
        print(f"\n⚠️  {failed} file(s) have syntax errors.")
        return False


if __name__ == "__main__":
    success = test_all_syntax()
    sys.exit(0 if success else 1)