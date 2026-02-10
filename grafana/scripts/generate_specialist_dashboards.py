#!/usr/bin/env python3
"""Generate Grafana dashboard JSON for each Big 11 specialist."""

import json
from pathlib import Path

SPECIALISTS = {
    "crush": {
        "title": "Crush Spread",
        "icon": "🫘",
        "color": "#FF6B6B",
        "inputs": ["ZL", "ZS", "ZM", "CFTC"],
    },
    "china": {
        "title": "China Demand",
        "icon": "🇨🇳",
        "color": "#E74C3C",
        "inputs": ["HG Copper", "CNY", "FXI"],
    },
    "fx": {
        "title": "FX Effects",
        "icon": "💱",
        "color": "#3498DB",
        "inputs": ["DXY", "BRL", "EUR"],
    },
    "fed": {
        "title": "Fed Policy",
        "icon": "🏛️",
        "color": "#27AE60",
        "inputs": ["FEDFUNDS", "DGS10", "T10Y2Y"],
    },
    "tariff": {
        "title": "Tariff Policy",
        "icon": "📜",
        "color": "#F39C12",
        "inputs": ["EPU Trade", "China TPU", "Duties"],
    },
    "energy": {
        "title": "Energy Complex",
        "icon": "⛽",
        "color": "#8E44AD",
        "inputs": ["CL Crude", "HO", "RB"],
    },
    "biofuel": {
        "title": "Biofuel Policy",
        "icon": "🌱",
        "color": "#1ABC9C",
        "inputs": ["D4 RIN", "RVO", "Biodiesel"],
    },
    "palm": {
        "title": "Palm Oil",
        "icon": "🌴",
        "color": "#F1C40F",
        "inputs": ["FCPO", "MYR", "Export Levy"],
    },
    "volatility": {
        "title": "Volatility Regime",
        "icon": "📊",
        "color": "#9B59B6",
        "inputs": ["VIX", "OVX", "VXGSCLS"],
    },
    "substitutes": {
        "title": "Substitute Oils",
        "icon": "🌻",
        "color": "#16A085",
        "inputs": ["Canola", "Sunflower", "Rapeseed"],
    },
    "trump_effect": {
        "title": "Trump Effect",
        "icon": "🎯",
        "color": "#E67E22",
        "inputs": ["EPU Daily", "DJT", "EMV Trade"],
    },
}


def stat(id, title, sql, x, y, w=4, h=4, color="green"):
    return {
        "datasource": {"type": "postgres", "uid": "${datasource}"},
        "type": "stat",
        "id": id,
        "title": title,
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "fieldConfig": {
            "defaults": {
                "color": {"mode": "thresholds"},
                "thresholds": {
                    "mode": "absolute",
                    "steps": [{"color": color, "value": None}],
                },
            }
        },
        "options": {
            "colorMode": "value",
            "graphMode": "none",
            "justifyMode": "center",
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
        },
        "targets": [
            {
                "datasource": {"type": "postgres", "uid": "${datasource}"},
                "format": "table",
                "rawQuery": True,
                "rawSql": sql,
                "refId": "A",
            }
        ],
    }


def ts(id, title, sql, x, y, w=24, h=10):
    return {
        "datasource": {"type": "postgres", "uid": "${datasource}"},
        "type": "timeseries",
        "id": id,
        "title": title,
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "fieldConfig": {
            "defaults": {
                "color": {"mode": "palette-classic"},
                "custom": {"lineWidth": 2, "showPoints": "never"},
            }
        },
        "options": {
            "legend": {"displayMode": "list", "placement": "bottom"},
            "tooltip": {"mode": "multi"},
        },
        "targets": [
            {
                "datasource": {"type": "postgres", "uid": "${datasource}"},
                "format": "time_series",
                "rawQuery": True,
                "rawSql": sql,
                "refId": "A",
            }
        ],
    }


def tbl(id, title, sql, x, y, w=12, h=8):
    return {
        "datasource": {"type": "postgres", "uid": "${datasource}"},
        "type": "table",
        "id": id,
        "title": title,
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "fieldConfig": {
            "defaults": {
                "color": {"mode": "thresholds"},
                "custom": {"align": "auto", "displayMode": "auto"},
            }
        },
        "options": {"showHeader": True, "cellHeight": "sm", "footer": {"show": False}},
        "targets": [
            {
                "datasource": {"type": "postgres", "uid": "${datasource}"},
                "format": "table",
                "rawQuery": True,
                "rawSql": sql,
                "refId": "A",
            }
        ],
    }


def row(id, title, y):
    return {
        "collapsed": False,
        "gridPos": {"h": 1, "w": 24, "x": 0, "y": y},
        "id": id,
        "panels": [],
        "title": title,
        "type": "row",
    }


def gauge(id, title, sql, x, y, w=6, h=5, min_val=0, max_val=100):
    return {
        "datasource": {"type": "postgres", "uid": "${datasource}"},
        "type": "gauge",
        "id": id,
        "title": title,
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "fieldConfig": {
            "defaults": {
                "color": {"mode": "thresholds"},
                "min": min_val,
                "max": max_val,
                "thresholds": {
                    "mode": "absolute",
                    "steps": [
                        {"color": "red", "value": None},
                        {"color": "yellow", "value": 30},
                        {"color": "green", "value": 50},
                    ],
                },
            }
        },
        "options": {
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}
        },
        "targets": [
            {
                "datasource": {"type": "postgres", "uid": "${datasource}"},
                "format": "table",
                "rawQuery": True,
                "rawSql": sql,
                "refId": "A",
            }
        ],
    }


def create_dashboard(name, cfg):
    s = name
    panels = [
        # === LIVE STATUS ROW ===
        row(100, f"{cfg['icon']} Live Status", 0),
        stat(
            1,
            "Total Predictions",
            f"SELECT COUNT(*) FROM training.oof_{s}_1d",
            0,
            1,
            4,
            4,
            "blue",
        ),
        stat(
            2,
            "Latest Date",
            f"SELECT MAX(trade_date)::text FROM training.oof_{s}_1d",
            4,
            1,
            4,
            4,
            "green",
        ),
        stat(
            3,
            "MAE (21d)",
            f"SELECT ROUND(AVG(ABS(p50-target_value))::numeric,4) FROM training.oof_{s}_1d WHERE horizon_days=21 AND target_value IS NOT NULL",
            8,
            1,
            4,
            4,
            "yellow",
        ),
        gauge(
            4,
            "Coverage % (21d)",
            f"SELECT ROUND(100.0*SUM(CASE WHEN target_value BETWEEN p30 AND p70 THEN 1 ELSE 0 END)/NULLIF(COUNT(*),0),1) FROM training.oof_{s}_1d WHERE horizon_days=21 AND target_value IS NOT NULL",
            12,
            1,
            6,
            4,
        ),
        stat(
            5,
            "Training Status",
            f"SELECT COALESCE((SELECT status FROM ops.training_runs WHERE specialist='{s}' ORDER BY started_at DESC LIMIT 1), 'Not Started')",
            18,
            1,
            3,
            4,
            "orange",
        ),
        stat(
            6,
            "Version",
            f"SELECT COALESCE((SELECT model_version FROM model.model_registry WHERE model_id LIKE '%{s}%' ORDER BY trained_at DESC LIMIT 1), 'N/A')",
            21,
            1,
            3,
            4,
            "purple",
        ),
        # === PREDICTIONS CHART ===
        row(101, "📈 OOF Predictions vs Actuals (21d Horizon)", 5),
        ts(
            10,
            "Quantile Forecast",
            f'SELECT trade_date as time, p30 as "P30 Low", p50 as "P50 Median", p70 as "P70 High", target_value as "Actual" FROM training.oof_{s}_1d WHERE horizon_days=21 ORDER BY trade_date',
            0,
            6,
            24,
            10,
        ),
        # === MULTI-HORIZON CONE ===
        row(102, "🎯 Multi-Horizon Forecast Cone", 16),
        ts(
            11,
            "5-Day Horizon",
            f"SELECT trade_date as time, p30, p50, p70, target_value FROM training.oof_{s}_1d WHERE horizon_days=5 ORDER BY trade_date",
            0,
            17,
            12,
            8,
        ),
        ts(
            12,
            "126-Day Horizon",
            f"SELECT trade_date as time, p30, p50, target_value FROM training.oof_{s}_1d WHERE horizon_days=126 ORDER BY trade_date",
            12,
            17,
            12,
            8,
        ),
        # === PERFORMANCE METRICS ===
        row(103, "📊 Performance by Horizon", 25),
        tbl(
            20,
            "Metrics Summary",
            f"""SELECT horizon_days as "Horizon", COUNT(*) as "N",
            ROUND(AVG(ABS(p50-target_value))::numeric,5) as "MAE",
            ROUND(100.0*SUM(CASE WHEN target_value BETWEEN p30 AND p70 THEN 1 ELSE 0 END)/NULLIF(COUNT(*),0),1) as "P30-P70 Cov%",
            ROUND(AVG(p50-target_value)::numeric,5) as "Bias"
            FROM training.oof_{s}_1d WHERE target_value IS NOT NULL GROUP BY horizon_days ORDER BY horizon_days""",
            0,
            26,
            12,
            8,
        ),
        tbl(
            21,
            "Latest 20 Predictions",
            f"SELECT trade_date, horizon_days as hz, ROUND(p30::numeric,4) as p30, ROUND(p50::numeric,4) as p50, ROUND(p70::numeric,4) as p70, ROUND(target_value::numeric,4) as actual FROM training.oof_{s}_1d ORDER BY trade_date DESC, horizon_days LIMIT 20",
            12,
            26,
            12,
            8,
        ),
        # === TRAINING RUNS ===
        row(104, "🔧 Recent Training Runs", 34),
        tbl(
            30,
            "Training History",
            f"SELECT run_id, horizon, status, started_at, ended_at, ROUND(EXTRACT(EPOCH FROM (ended_at-started_at))/60)::int as \"Mins\" FROM ops.training_runs WHERE specialist='{s}' ORDER BY started_at DESC LIMIT 8",
            0,
            35,
            16,
            6,
        ),
        stat(
            31,
            "Last Train",
            f"SELECT TO_CHAR(MAX(started_at), 'YYYY-MM-DD HH24:MI') FROM ops.training_runs WHERE specialist='{s}'",
            16,
            35,
            4,
            3,
            "blue",
        ),
        stat(
            32,
            "Runs (7d)",
            f"SELECT COUNT(*) FROM ops.training_runs WHERE specialist='{s}' AND started_at > NOW()-INTERVAL '7 days'",
            20,
            35,
            4,
            3,
            "green",
        ),
        stat(
            33,
            "Failed",
            f"SELECT COUNT(*) FROM ops.training_runs WHERE specialist='{s}' AND status='failed'",
            16,
            38,
            4,
            3,
            "red",
        ),
        stat(
            34,
            "Avg Duration",
            f"SELECT ROUND(AVG(EXTRACT(EPOCH FROM (ended_at-started_at))/60))::int FROM ops.training_runs WHERE specialist='{s}' AND status='completed'",
            20,
            38,
            4,
            3,
            "yellow",
        ),
        # === DATA SOURCE FRESHNESS ===
        row(105, "📡 Data Source Freshness", 41),
    ]
    # Add input data freshness stats
    for i, inp in enumerate(cfg["inputs"][:4]):
        panels.append(
            stat(
                40 + i,
                inp,
                f"SELECT ROUND(EXTRACT(EPOCH FROM (NOW()-MAX(updated_at)))/3600)::int || 'h ago' FROM ops.data_quality_metrics WHERE source_name ILIKE '%{inp.split()[0].lower()}%' LIMIT 1",
                i * 6,
                42,
                6,
                3,
                "green",
            )
        )

    # === CREATIVE: ERROR DISTRIBUTION ===
    y = 45
    panels.append(row(106, "📉 Error Analysis", y))
    panels.append(
        ts(
            50,
            "Prediction Error Over Time (21d)",
            f'SELECT trade_date as time, (p50 - target_value) as "Error" FROM training.oof_{s}_1d WHERE horizon_days=21 AND target_value IS NOT NULL ORDER BY trade_date',
            0,
            y + 1,
            12,
            8,
        )
    )
    panels.append(
        ts(
            51,
            "Interval Width (P70-P30)",
            f'SELECT trade_date as time, (p70-p30) as "Width" FROM training.oof_{s}_1d WHERE horizon_days=21 ORDER BY trade_date',
            12,
            y + 1,
            12,
            8,
        )
    )

    return {
        "annotations": {"list": []},
        "editable": True,
        "fiscalYearStartMonth": 0,
        "graphTooltip": 1,
        "id": None,
        "links": [],
        "liveNow": False,
        "panels": panels,
        "schemaVersion": 39,
        "tags": ["specialist", s, "zinc-fusion"],
        "templating": {
            "list": [
                {
                    "current": {},
                    "hide": 0,
                    "includeAll": False,
                    "label": "Data Source",
                    "multi": False,
                    "name": "datasource",
                    "options": [],
                    "query": "postgres",
                    "refresh": 1,
                    "type": "datasource",
                }
            ]
        },
        "time": {"from": "now-90d", "to": "now"},
        "timepicker": {},
        "timezone": "browser",
        "title": f"{cfg['icon']} {cfg['title']} Specialist",
        "uid": f"specialist-{s}",
        "version": 1,
        "description": f"Dashboard for {cfg['title']} specialist model - one of the Big 11",
    }


def main():
    out_dir = Path(__file__).parent.parent / "grafana" / "dashboards" / "specialists"
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, cfg in SPECIALISTS.items():
        dash = create_dashboard(name, cfg)
        path = out_dir / f"specialist-{name}.json"
        with open(path, "w") as f:
            json.dump(dash, f, indent=2)
        print(f"✅ Created {path}")
    print(f"\n🎉 Generated {len(SPECIALISTS)} specialist dashboards in {out_dir}")


if __name__ == "__main__":
    main()
