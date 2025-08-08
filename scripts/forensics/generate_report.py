#!/usr/bin/env python3
"""
Forensic Report Generator
Generates HTML and Markdown reports summarizing:
- User profiles found
- Office/Outlook artifacts per user
- Registry findings
- PST files discovered
- High-priority items for counsel review
"""
import os, sys, json, re, hashlib
from pathlib import Path
from datetime import datetime
from collections import defaultdict

ROOT = Path(sys.argv[1] if len(sys.argv)>1 else "artifact_dump").resolve()
OUT_HTML = Path(sys.argv[2] if len(sys.argv)>2 else "forensic_report.html")
OUT_MD = OUT_HTML.with_suffix(".md")

def get_users_from_paths(paths):
    """Extract unique usernames from Windows paths"""
    users = set()
    for p in paths:
        # Match patterns like Users\Username\ or Users/Username/
        m = re.search(r'Users[/\\]([^/\\]+)[/\\]', str(p), re.IGNORECASE)
        if m:
            users.add(m.group(1))
    return sorted(users)

def categorize_artifacts(artifacts):
    """Group artifacts by type and user"""
    by_user = defaultdict(lambda: defaultdict(list))
    
    for art in artifacts:
        p = Path(art)
        user = None
        m = re.search(r'Users[/\\]([^/\\]+)[/\\]', str(p), re.IGNORECASE)
        if m:
            user = m.group(1)
        else:
            user = "_system"
            
        # Categorize by type
        s = str(p).lower()
        if "officecache" in s or "officefilecache" in s:
            by_user[user]["office_cache"].append(art)
        elif "unsavedfiles" in s:
            by_user[user]["unsaved_files"].append(art)
        elif "content.outlook" in s or r"\olk" in s:
            by_user[user]["outlook_temp"].append(art)
        elif "roamcache" in s:
            by_user[user]["outlook_roamcache"].append(art)
        elif ".pst" in s:
            by_user[user]["pst_files"].append(art)
        elif ".ost" in s:
            by_user[user]["ost_files"].append(art)
        elif "teams" in s:
            by_user[user]["teams"].append(art)
        elif "onenote" in s:
            by_user[user]["onenote"].append(art)
        elif "recent" in s:
            by_user[user]["recent_files"].append(art)
        else:
            by_user[user]["other"].append(art)
            
    return dict(by_user)

def parse_registry_findings(reg_index_path):
    """Parse registry extraction results"""
    findings = defaultdict(dict)
    
    if not reg_index_path.exists():
        return {}
        
    with open(reg_index_path) as f:
        data = json.load(f)
        
    for hive_info in data.get("processed", []):
        if "error" in hive_info:
            continue
            
        # Extract user from hive path
        user = "_system"
        m = re.search(r'Users[/\\]([^/\\]+)[/\\]', hive_info["hive"], re.IGNORECASE)
        if m:
            user = m.group(1)
            
        # Read targets if available
        if "targets_path_json" in hive_info:
            targets_path = ROOT.parent / hive_info["targets_path_json"]
            if targets_path.exists():
                with open(targets_path) as f:
                    targets = json.load(f)
                    
                # Extract key findings
                if "outlook_secure_temp_folder" in targets:
                    findings[user]["outlook_temp_path"] = targets["outlook_secure_temp_folder"]
                    
                if "office_resiliency" in targets and targets["office_resiliency"]:
                    findings[user]["office_crashes"] = len(targets["office_resiliency"].get("subkeys", []))
                    
                for mru_type in ["word_mru", "excel_mru", "ppt_mru"]:
                    if mru_type in targets and targets[mru_type]:
                        findings[user][mru_type] = targets[mru_type].get("values", {})
                        
                if "recent_docs" in targets and targets["recent_docs"]:
                    findings[user]["recent_docs_count"] = len(targets["recent_docs"].get("values", {}))
                    
                if "typed_urls" in targets and targets["typed_urls"]:
                    findings[user]["typed_urls"] = list(targets["typed_urls"].get("values", {}).values())
                    
    return dict(findings)

def format_size(nbytes):
    """Format bytes as human readable"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if nbytes < 1024.0:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024.0
    return f"{nbytes:.1f} PB"

def generate_markdown(data):
    """Generate Markdown report"""
    lines = []
    lines.append("# Forensic Analysis Report")
    lines.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"\nArtifact Directory: `{ROOT}`")
    
    # Summary
    lines.append("\n## Summary")
    lines.append(f"- **Users Found**: {len([u for u in data['by_user'] if u != '_system'])}")
    lines.append(f"- **Total Artifacts**: {data['total_artifacts']}")
    lines.append(f"- **PST Files**: {data['pst_count']}")
    lines.append(f"- **Registry Hives Processed**: {len(data.get('registry_findings', {}))}")
    
    # High Priority Items
    if data['high_priority']:
        lines.append("\n## High Priority Items")
        for item in data['high_priority']:
            lines.append(f"- {item}")
    
    # Per-User Findings
    lines.append("\n## User Analysis")
    
    for user in sorted(data['by_user'].keys()):
        if user == "_system":
            continue
            
        lines.append(f"\n### {user}")
        
        user_data = data['by_user'][user]
        reg_data = data['registry_findings'].get(user, {})
        
        # Key artifacts
        if user_data.get('pst_files'):
            lines.append(f"\n**PST Files** ({len(user_data['pst_files'])})")
            for pst in user_data['pst_files'][:5]:
                lines.append(f"- `{pst}`")
            if len(user_data['pst_files']) > 5:
                lines.append(f"- ... and {len(user_data['pst_files'])-5} more")
                
        if user_data.get('unsaved_files'):
            lines.append(f"\n**Unsaved Office Files** ({len(user_data['unsaved_files'])})")
            for f in user_data['unsaved_files'][:5]:
                lines.append(f"- `{f}`")
                
        if user_data.get('outlook_temp'):
            lines.append(f"\n**Outlook Temporary Files** ({len(user_data['outlook_temp'])})")
            if reg_data.get('outlook_temp_path'):
                lines.append(f"- Registry path: `{reg_data['outlook_temp_path']}`")
                
        # Registry findings
        if reg_data:
            lines.append("\n**Registry Findings**")
            if reg_data.get('office_crashes'):
                lines.append(f"- Office crash/recovery entries: {reg_data['office_crashes']}")
            if reg_data.get('recent_docs_count'):
                lines.append(f"- Recent documents: {reg_data['recent_docs_count']}")
            if reg_data.get('typed_urls'):
                lines.append(f"- Typed URLs: {len(reg_data['typed_urls'])}")
                for url in reg_data['typed_urls'][:3]:
                    lines.append(f"  - `{url}`")
                    
        # Stats
        total_arts = sum(len(v) for v in user_data.values())
        lines.append(f"\nTotal artifacts for {user}: **{total_arts}**")
    
    # System artifacts
    if "_system" in data['by_user']:
        lines.append("\n### System-Level Artifacts")
        sys_data = data['by_user']['_system']
        total = sum(len(v) for v in sys_data.values())
        lines.append(f"Total system artifacts: **{total}**")
    
    return "\n".join(lines)

def generate_html(data, markdown_content):
    """Generate HTML report with styling"""
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Forensic Analysis Report</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        h1, h2, h3 {{
            color: #2c3e50;
            border-bottom: 2px solid #3498db;
            padding-bottom: 10px;
        }}
        .summary {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }}
        .user-section {{
            background: white;
            padding: 20px;
            margin-bottom: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .high-priority {{
            background: #fee;
            border-left: 4px solid #e74c3c;
            padding: 10px;
            margin: 10px 0;
        }}
        code {{
            background: #f4f4f4;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'Consolas', 'Monaco', monospace;
            font-size: 0.9em;
        }}
        .artifact-list {{
            max-height: 200px;
            overflow-y: auto;
            background: #f9f9f9;
            padding: 10px;
            border-radius: 4px;
            margin: 10px 0;
        }}
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }}
        .stat-box {{
            background: #3498db;
            color: white;
            padding: 15px;
            border-radius: 6px;
            text-align: center;
        }}
        .stat-box h3 {{
            margin: 0;
            color: white;
            border: none;
        }}
        .stat-box .number {{
            font-size: 2em;
            font-weight: bold;
        }}
        .timestamp {{
            color: #7f8c8d;
            font-style: italic;
        }}
    </style>
</head>
<body>
    <h1>Forensic Analysis Report</h1>
    <p class="timestamp">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    
    <div class="summary">
        <h2>Summary</h2>
        <div class="stats">
            <div class="stat-box">
                <h3>Users Found</h3>
                <div class="number">{len([u for u in data['by_user'] if u != '_system'])}</div>
            </div>
            <div class="stat-box">
                <h3>Total Artifacts</h3>
                <div class="number">{data['total_artifacts']}</div>
            </div>
            <div class="stat-box">
                <h3>PST Files</h3>
                <div class="number">{data['pst_count']}</div>
            </div>
            <div class="stat-box">
                <h3>Registry Hives</h3>
                <div class="number">{len(data.get('registry_findings', {}))}</div>
            </div>
        </div>
    </div>
"""
    
    # High priority section
    if data['high_priority']:
        html += """
    <div class="high-priority">
        <h2>High Priority Items</h2>
        <ul>
"""
        for item in data['high_priority']:
            html += f"            <li>{item}</li>\n"
        html += "        </ul>\n    </div>\n"
    
    # User sections
    html += "\n    <h2>User Analysis</h2>\n"
    
    for user in sorted(data['by_user'].keys()):
        if user == "_system":
            continue
            
        user_data = data['by_user'][user]
        reg_data = data['registry_findings'].get(user, {})
        total_arts = sum(len(v) for v in user_data.values())
        
        html += f"""
    <div class="user-section">
        <h3>{user}</h3>
        <p>Total artifacts: <strong>{total_arts}</strong></p>
"""
        
        # PST files
        if user_data.get('pst_files'):
            html += f"        <h4>PST Files ({len(user_data['pst_files'])})</h4>\n"
            html += '        <div class="artifact-list">\n'
            for pst in user_data['pst_files']:
                html += f"            <code>{pst}</code><br>\n"
            html += "        </div>\n"
            
        # Unsaved files
        if user_data.get('unsaved_files'):
            html += f"        <h4>Unsaved Office Files ({len(user_data['unsaved_files'])})</h4>\n"
            html += '        <div class="artifact-list">\n'
            for f in user_data['unsaved_files'][:10]:
                html += f"            <code>{f}</code><br>\n"
            if len(user_data['unsaved_files']) > 10:
                html += f"            <em>... and {len(user_data['unsaved_files'])-10} more</em>\n"
            html += "        </div>\n"
            
        # Registry findings
        if reg_data:
            html += "        <h4>Registry Findings</h4>\n        <ul>\n"
            if reg_data.get('outlook_temp_path'):
                html += f"            <li>Outlook temp path: <code>{reg_data['outlook_temp_path']}</code></li>\n"
            if reg_data.get('office_crashes'):
                html += f"            <li>Office crash/recovery entries: {reg_data['office_crashes']}</li>\n"
            if reg_data.get('recent_docs_count'):
                html += f"            <li>Recent documents: {reg_data['recent_docs_count']}</li>\n"
            if reg_data.get('typed_urls'):
                html += f"            <li>Typed URLs: {len(reg_data['typed_urls'])}</li>\n"
            html += "        </ul>\n"
            
        html += "    </div>\n"
    
    html += """
</body>
</html>"""
    
    return html

def main():
    # Load artifact index
    artifacts = []
    artifact_index = ROOT / "_index.json"
    if artifact_index.exists():
        with open(artifact_index) as f:
            data = json.load(f)
            artifacts = data.get("artifacts", [])
    
    # Load registry findings
    registry_findings = parse_registry_findings(ROOT / "registry" / "_registry_index.json")
    
    # Process data
    by_user = categorize_artifacts(artifacts)
    
    # Count PST files
    pst_count = sum(len(u.get("pst_files", [])) for u in by_user.values())
    
    # Identify high priority items
    high_priority = []
    
    # Check for unsaved files
    unsaved_count = sum(len(u.get("unsaved_files", [])) for u in by_user.values())
    if unsaved_count > 0:
        high_priority.append(f"Found {unsaved_count} unsaved Office files that may contain unrecovered work")
    
    # Check for large PST files
    large_psts = []
    for user_arts in by_user.values():
        for pst in user_arts.get("pst_files", []):
            pst_path = ROOT / pst
            if pst_path.exists():
                size = pst_path.stat().st_size
                if size > 1024*1024*1024:  # > 1GB
                    large_psts.append((pst, size))
    
    if large_psts:
        high_priority.append(f"Found {len(large_psts)} PST files larger than 1GB")
    
    # Check for crash data
    crash_users = [u for u,d in registry_findings.items() if d.get("office_crashes", 0) > 0]
    if crash_users:
        high_priority.append(f"Office crash/recovery data found for users: {', '.join(crash_users)}")
    
    # Build report data
    report_data = {
        "by_user": by_user,
        "registry_findings": registry_findings,
        "total_artifacts": len(artifacts),
        "pst_count": pst_count,
        "high_priority": high_priority,
        "artifact_root": str(ROOT),
        "generated": datetime.now().isoformat()
    }
    
    # Generate reports
    markdown_content = generate_markdown(report_data)
    html_content = generate_html(report_data, markdown_content)
    
    # Write files
    OUT_MD.write_text(markdown_content, encoding='utf-8')
    OUT_HTML.write_text(html_content, encoding='utf-8')
    
    print(json.dumps({
        "markdown_report": str(OUT_MD),
        "html_report": str(OUT_HTML),
        "users_found": len([u for u in by_user if u != "_system"]),
        "total_artifacts": len(artifacts),
        "high_priority_items": len(high_priority)
    }, indent=2))

if __name__ == "__main__":
    main()