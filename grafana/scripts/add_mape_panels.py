#!/usr/bin/env python3
"""Add MAPE by Horizon row and panels to all specialist dashboards."""
import json
import os

SPECIALIST_OOF = {
    'biofuel': 'training.oof_biofuel_1d',
    'china': 'training.oof_china_1d',
    'core': 'training.oof_core_1d',
    'crush': 'training.oof_crush_1d',
    'energy': 'training.oof_energy_1d',
    'fed': 'training.oof_fed_1d',
    'fx': 'training.oof_fx_1d',
    'palm': 'training.oof_palm_1d',
    'substitutes': 'training.oof_substitutes_1d',
    'tariff': 'training.oof_tariff_1d',
    'trump_effect': 'training.oof_trump_effect_1d',
    'volatility': 'training.oof_volatility_1d',
}

def create_mape_row():
    return {"collapsed": False, "gridPos": {"h": 1, "w": 24, "x": 0, "y": 5},
            "id": 110, "panels": [], "title": "📊 MAPE by Horizon", "type": "row"}

def create_mape_panel(horizon, oof_table):
    x_pos = {5: 0, 21: 6, 63: 12, 126: 18}
    ids = {5: 111, 21: 112, 63: 113, 126: 114}
    return {
        "datasource": {"type": "postgres", "uid": "${datasource}"},
        "fieldConfig": {"defaults": {"color": {"mode": "thresholds"}, "decimals": 2, "unit": "percent",
            "thresholds": {"mode": "absolute", "steps": [
                {"color": "light-green", "value": None}, {"color": "yellow", "value": 8}, {"color": "red", "value": 15}
            ]}}, "overrides": []},
        "gridPos": {"h": 4, "w": 6, "x": x_pos[horizon], "y": 6},
        "id": ids[horizon],
        "options": {"colorMode": "value", "graphMode": "none", "justifyMode": "auto", "orientation": "auto",
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "textMode": "auto"},
        "targets": [{"datasource": {"type": "postgres", "uid": "${datasource}"}, "format": "table", "rawQuery": True,
            "rawSql": f"SELECT ROUND(100.0 * AVG(ABS((p50-target_value)/NULLIF(target_value,0)))::numeric, 2) as mape FROM {oof_table} WHERE horizon_days={horizon} AND target_value IS NOT NULL",
            "refId": "A"}],
        "title": f"MAPE ({horizon}d)", "type": "stat"
    }

def add_mape_panels(filepath, specialist):
    oof_table = SPECIALIST_OOF.get(specialist)
    if not oof_table:
        return False
    with open(filepath, 'r') as f:
        dashboard = json.load(f)
    if any(p.get('id') == 110 for p in dashboard['panels']):
        print("  Already has MAPE row")
        return False
    # Shift panels down
    for panel in dashboard['panels']:
        if panel['gridPos']['y'] >= 5:
            panel['gridPos']['y'] += 5
    # Create and insert
    mape_row = create_mape_row()
    mape_panels = [create_mape_panel(h, oof_table) for h in [5, 21, 63, 126]]
    insert_idx = next((i for i, p in enumerate(dashboard['panels']) if p['gridPos']['y'] >= 10), len(dashboard['panels']))
    dashboard['panels'] = dashboard['panels'][:insert_idx] + [mape_row] + mape_panels + dashboard['panels'][insert_idx:]
    with open(filepath, 'w') as f:
        json.dump(dashboard, f, indent=2)
    return True

if __name__ == '__main__':
    dashboard_dir = 'grafana/dashboards/specialists'
    for fname in sorted(os.listdir(dashboard_dir)):
        if fname.endswith('.json') and fname.startswith('specialist-'):
            specialist = fname.replace('specialist-', '').replace('.json', '')
            filepath = os.path.join(dashboard_dir, fname)
            if specialist == 'trump_effect':
                print(f"{fname}: ✅ Already complete")
                continue
            print(f"{fname}: ", end="")
            if add_mape_panels(filepath, specialist):
                print("✅ Added MAPE row and panels")
            else:
                print("⚠️ Skipped")
    print("\n✅ All dashboards updated!")

