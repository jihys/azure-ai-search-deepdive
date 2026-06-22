#!/bin/bash
# ============================================
# Bicep Template Validation
# Validates all Bicep files for syntax errors
# ============================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== Bicep Syntax Validation ==="

environments=("sweden" "korea" "sweden-public")
errors=0

for env in "${environments[@]}"; do
    main_file="$INFRA_DIR/$env/main.bicep"
    if [ -f "$main_file" ]; then
        echo ""
        echo "Validating $env environment..."
        if az bicep build --file "$main_file" > /dev/null 2>&1; then
            echo "✓ $env: Bicep syntax valid"
        else
            echo "✗ $env: Bicep syntax error"
            az bicep build --file "$main_file"
            ((errors++))
        fi
    else
        echo "⚠ $env/main.bicep not found"
    fi
done

echo ""
if [ $errors -eq 0 ]; then
    echo "✓ All Bicep templates are valid"
    exit 0
else
    echo "✗ Found $errors Bicep template error(s)"
    exit 1
fi
