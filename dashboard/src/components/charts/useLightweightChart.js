import { createChart, LineSeries, AreaSeries } from 'lightweight-charts';

export function useLightweightChart(container, options = {}) {
  return createChart(container, {
    width: container.clientWidth,
    height: options.height || 400,
    layout: { background: { color: '#0B0F14' }, textColor: '#AEB6C1' },
    grid: { vertLines: { visible: false }, horzLines: { color: 'rgba(255,255,255,0.04)' } },
    rightPriceScale: { borderVisible: false },
    timeScale: { borderVisible: false },
  });
}

export function addPriceSeries(chart) {
  return chart.addSeries(LineSeries, { color: '#60A5FA', lineWidth: 2 });
}

export function addP50Series(chart) {
  return chart.addSeries(LineSeries, { color: '#E5E7EB', lineWidth: 1.5 });
}

export function addP10Series(chart) {
  return chart.addSeries(AreaSeries, { topColor: 'rgba(74,222,128,0)', bottomColor: 'rgba(74,222,128,0.15)', lineColor: 'rgba(74,222,128,0.4)', lineWidth: 1 });
}

export function addP90Series(chart) {
  return chart.addSeries(AreaSeries, { topColor: 'rgba(248,113,113,0.15)', bottomColor: 'rgba(248,113,113,0)', lineColor: 'rgba(248,113,113,0.4)', lineWidth: 1 });
}

export function addShapSeries(chart) {
  return chart.addSeries(LineSeries, { color: 'rgba(74,222,128,0.35)', lineWidth: 1, priceScaleId: 'left' });
}

export function updateShapColor(series, color) {
  if (!series) return;
  series.applyOptions({ color });
}

export function createMarkers(events = []) {
  return events.map(e => ({
    time: e.time,
    position: 'aboveBar',
    color: '#94A3B8',
    shape: 'circle',
    text: e.label,
  }));
}

export default {
  useLightweightChart,
  addPriceSeries,
  addP50Series,
  addP10Series,
  addP90Series,
  addShapSeries,
  updateShapColor,
  createMarkers,
};
