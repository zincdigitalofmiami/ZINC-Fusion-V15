#!/usr/bin/env python3
"""
MODEL VISIBILITY DASHBOARD
Simple HTML page showing ALL your fucking models
"""

import os
import json
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path("/Volumes/Satechi Hub/ZINC-FUSION-V15")
MODELS_DIR = PROJECT_ROOT / "models"

def scan_models():
    """Scan all model directories and collect info"""
    models = []
    
    for root, dirs, files in os.walk(MODELS_DIR):
        root_path = Path(root)
        
        # Skip hidden and cache directories
        if any(part.startswith('.') for part in root_path.parts):
            continue
        
        # Look for AutoGluon predictor directories
        if 'predictor.pkl' in files or any(f.endswith('.pkl') for f in files):
            rel_path = root_path.relative_to(MODELS_DIR)
            
            model_info = {
                'path': str(rel_path),
                'full_path': str(root_path),
                'files': sorted(files),
                'size_mb': sum(os.path.getsize(root_path / f) for f in files if not f.startswith('.')) / (1024*1024),
                'modified': datetime.fromtimestamp(os.path.getmtime(root_path)).strftime('%Y-%m-%d %H:%M')
            }
            
            # Try to load model info
            info_file = root_path / 'info.json'
            if info_file.exists():
                try:
                    with open(info_file) as f:
                        model_info['metadata'] = json.load(f)
                except:
                    pass
            
            models.append(model_info)
    
    return sorted(models, key=lambda x: x['path'])

def generate_html(models):
    """Generate HTML dashboard"""
    
    html = """<!DOCTYPE html>
<html>
<head>
    <title>ZINC-FUSION-V15 Model Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: 'Monaco', 'Courier New', monospace; 
            background: #0a0a0a; 
            color: #00ff00;
            padding: 20px;
        }
        h1 { 
            color: #00ff00; 
            margin-bottom: 10px;
            font-size: 24px;
        }
        .stats {
            background: #1a1a1a;
            padding: 15px;
            margin-bottom: 20px;
            border: 1px solid #00ff00;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
        }
        .stat {
            padding: 10px;
            border-left: 3px solid #00ff00;
        }
        .stat-value {
            font-size: 32px;
            font-weight: bold;
            color: #00ff00;
        }
        .stat-label {
            color: #888;
            font-size: 12px;
        }
        .model {
            background: #1a1a1a;
            padding: 15px;
            margin-bottom: 15px;
            border-left: 4px solid #00ff00;
        }
        .model:hover {
            background: #2a2a2a;
            border-left-color: #00ffff;
        }
        .model-path {
            font-size: 16px;
            font-weight: bold;
            color: #00ffff;
            margin-bottom: 8px;
        }
        .model-details {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 10px;
            margin-top: 10px;
            padding-top: 10px;
            border-top: 1px solid #333;
        }
        .detail {
            color: #888;
            font-size: 12px;
        }
        .detail-value {
            color: #00ff00;
            font-weight: bold;
        }
        .files {
            margin-top: 8px;
            padding: 8px;
            background: #0a0a0a;
            font-size: 11px;
            color: #666;
            max-height: 100px;
            overflow-y: auto;
        }
        .metadata {
            margin-top: 10px;
            padding: 10px;
            background: #0a0a0a;
            border-left: 2px solid #666;
            font-size: 11px;
        }
        .timestamp {
            color: #666;
            font-size: 11px;
            margin-top: 20px;
            text-align: center;
        }
        .filter {
            margin-bottom: 20px;
            padding: 10px;
            background: #1a1a1a;
            border: 1px solid #333;
        }
        .filter input {
            width: 100%;
            padding: 8px;
            background: #0a0a0a;
            border: 1px solid #00ff00;
            color: #00ff00;
            font-family: inherit;
            font-size: 14px;
        }
        .filter input:focus {
            outline: none;
            border-color: #00ffff;
        }
    </style>
</head>
<body>
    <h1>🚀 ZINC-FUSION-V15 MODEL DASHBOARD</h1>
    
    <div class="stats">
        <div class="stat">
            <div class="stat-value">""" + str(len(models)) + """</div>
            <div class="stat-label">TOTAL MODELS</div>
        </div>
        <div class="stat">
            <div class="stat-value">""" + str(sum(m['size_mb'] for m in models)) + """ MB</div>
            <div class="stat-label">TOTAL SIZE</div>
        </div>
        <div class="stat">
            <div class="stat-value">""" + str(len(set(m['path'].split('/')[0] for m in models))) + """</div>
            <div class="stat-label">CATEGORIES</div>
        </div>
    </div>
    
    <div class="filter">
        <input type="text" id="search" placeholder="🔍 Filter models..." onkeyup="filterModels()">
    </div>
    
    <div id="models">
"""
    
    for model in models:
        html += f"""
        <div class="model" data-path="{model['path']}">
            <div class="model-path">{model['path']}</div>
            <div class="model-details">
                <div class="detail">
                    Size: <span class="detail-value">{model['size_mb']:.1f} MB</span>
                </div>
                <div class="detail">
                    Modified: <span class="detail-value">{model['modified']}</span>
                </div>
                <div class="detail">
                    Files: <span class="detail-value">{len(model['files'])}</span>
                </div>
            </div>
            <div class="files">
                {' | '.join(model['files'][:10])}
                {'...' if len(model['files']) > 10 else ''}
            </div>
"""
        
        if 'metadata' in model:
            html += f"""
            <div class="metadata">
                <pre>{json.dumps(model['metadata'], indent=2)}</pre>
            </div>
"""
        
        html += """        </div>
"""
    
    html += """
    </div>
    
    <div class="timestamp">
        Generated: """ + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + """
    </div>
    
    <script>
        function filterModels() {
            const search = document.getElementById('search').value.toLowerCase();
            const models = document.querySelectorAll('.model');
            
            models.forEach(model => {
                const path = model.getAttribute('data-path').toLowerCase();
                if (path.includes(search)) {
                    model.style.display = 'block';
                } else {
                    model.style.display = 'none';
                }
            });
        }
    </script>
</body>
</html>
"""
    
    return html

if __name__ == '__main__':
    print("Scanning models directory...")
    models = scan_models()
    
    print(f"Found {len(models)} models")
    
    print("Generating HTML...")
    html = generate_html(models)
    
    output_file = PROJECT_ROOT / "MODEL_DASHBOARD.html"
    with open(output_file, 'w') as f:
        f.write(html)
    
    print(f"✓ Dashboard created: {output_file}")
    print(f"✓ Open in browser: file://{output_file}")
