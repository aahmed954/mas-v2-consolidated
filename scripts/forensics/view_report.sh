#!/usr/bin/env bash
# Quick report viewer - opens in browser or shows path

REPORT="${1:-forensic_report.html}"

if [ ! -f "$REPORT" ]; then
    echo "Report not found: $REPORT"
    echo "Run the forensic analysis first to generate the report."
    exit 1
fi

echo "Report generated at: $(realpath "$REPORT")"
echo "Also available as: $(realpath "${REPORT%.html}.md")"

# Try to open in browser
if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$REPORT" 2>/dev/null &
    echo "Opening in browser..."
elif command -v open >/dev/null 2>&1; then
    open "$REPORT" 2>/dev/null &
    echo "Opening in browser..."
else
    echo "Copy this path to view in a browser:"
    echo "file://$(realpath "$REPORT")"
fi

# Show summary
echo -e "\nReport Summary:"
if command -v python3 >/dev/null 2>&1; then
    python3 -c "
import json
with open('artifact_dump/_index.json', 'r') as f:
    data = json.load(f)
    print(f'  Total artifacts: {len(data.get(\"artifacts\", []))}')
    
with open('artifact_dump/registry/_registry_index.json', 'r') as f:
    data = json.load(f)
    print(f'  Registry hives processed: {len(data.get(\"processed\", []))}')
" 2>/dev/null || echo "  (Run forensic analysis to see summary)"
fi