import React from 'react';
import { Product, SupplierTerms } from '../types';

interface DepletionChartProps {
  product: Product;
  supplierTerms: SupplierTerms;
  eligibleIncoming?: number;
}

export const DepletionChart: React.FC<DepletionChartProps> = ({
  product,
  supplierTerms,
  eligibleIncoming = 0,
}) => {
  // Baseline rate: 4.0 units / day
  const dailyDemand = 4.0;
  const initialStock = product.current_stock;
  const days = 30;
  const leadTimeDays = supplierTerms.lead_time_days; // e.g. 14

  // Points for 30 days
  const points: { day: number; stock: number }[] = [];
  for (let d = 0; d <= days; d++) {
    // If incoming order exists and arrives on day 5 (e.g. TC3)
    let stock = initialStock - d * dailyDemand;
    if (eligibleIncoming > 0 && d >= 5) {
      stock += eligibleIncoming;
    }
    points.push({ day: d, stock: Math.max(0, Math.round(stock * 10) / 10) });
  }

  // Calculate day of stockout without new order
  const stockoutDay =
    eligibleIncoming === 0 && dailyDemand > 0
      ? Math.floor(initialStock / dailyDemand)
      : null;

  // SVG dimensions
  const svgWidth = 650;
  const svgHeight = 220;
  const padding = { top: 25, right: 30, bottom: 35, left: 50 };
  const graphWidth = svgWidth - padding.left - padding.right;
  const graphHeight = svgHeight - padding.top - padding.bottom;

  const maxStock = Math.max(60, initialStock + eligibleIncoming + 10);

  const getX = (day: number) => padding.left + (day / days) * graphWidth;
  const getY = (val: number) => padding.top + graphHeight - (val / maxStock) * graphHeight;

  const pathD = points
    .map((pt, idx) => `${idx === 0 ? 'M' : 'L'} ${getX(pt.day)} ${getY(pt.stock)}`)
    .join(' ');

  const reorderPointY = getY(Math.round(dailyDemand * leadTimeDays));

  return (
    <div className="depletion-chart-container" aria-label="30-Day Inventory Depletion Chart">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
        <div>
          <h4 style={{ margin: 0, fontSize: '0.95rem', color: 'var(--color-deep-aubergine)' }}>
            30-Day Depletion &amp; Lead-Time Horizon &bull; <span className="mono">{product.sku}</span>
          </h4>
          <span style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
            Illustrative forecast based on verified 4.0 units/day sales demand rate
          </span>
        </div>
        <span
          className="badge"
          style={{
            backgroundColor: stockoutDay !== null && stockoutDay <= leadTimeDays ? 'var(--color-danger-bg)' : 'var(--color-success-bg)',
            color: stockoutDay !== null && stockoutDay <= leadTimeDays ? 'var(--color-danger)' : 'var(--color-success)',
          }}
        >
          {stockoutDay !== null
            ? `Stockout in ~${stockoutDay} days`
            : eligibleIncoming > 0
            ? 'Covered by Incoming PO'
            : 'Sufficient Stock'}
        </span>
      </div>

      <div className="chart-legend">
        <div className="legend-item">
          <span className="legend-color-box" style={{ backgroundColor: 'var(--color-deep-aubergine)' }} />
          <span>Projected Stock Level</span>
        </div>
        <div className="legend-item">
          <span className="legend-color-box" style={{ backgroundColor: 'var(--color-marigold)' }} />
          <span>Lead-Time Horizon ({leadTimeDays}d)</span>
        </div>
        <div className="legend-item">
          <span className="legend-color-box" style={{ backgroundColor: 'var(--color-danger)' }} />
          <span>Stockout Threshold (0 units)</span>
        </div>
      </div>

      <svg
        viewBox={`0 0 ${svgWidth} ${svgHeight}`}
        style={{ width: '100%', height: 'auto', overflow: 'visible' }}
        role="img"
        aria-label={`Trajectory for ${product.sku}`}
      >
        {/* Grid lines */}
        <line
          x1={padding.left}
          y1={getY(0)}
          x2={svgWidth - padding.right}
          y2={getY(0)}
          stroke="#C9D0D8"
          strokeWidth="1.5"
        />
        <line
          x1={padding.left}
          y1={reorderPointY}
          x2={svgWidth - padding.right}
          y2={reorderPointY}
          stroke="#EAAA00"
          strokeWidth="1"
          strokeDasharray="4 4"
        />

        {/* Lead time vertical boundary line */}
        <line
          x1={getX(leadTimeDays)}
          y1={padding.top}
          x2={getX(leadTimeDays)}
          y2={padding.top + graphHeight}
          stroke="#EAAA00"
          strokeWidth="1.5"
          strokeDasharray="3 3"
        />
        <text
          x={getX(leadTimeDays) + 4}
          y={padding.top + 12}
          fill="#8C6500"
          fontSize="10"
          fontWeight="700"
          fontFamily="var(--font-sans)"
        >
          Lead Time ({leadTimeDays}d)
        </text>

        {/* Depletion curve area fill */}
        <path
          d={`${pathD} L ${getX(days)} ${getY(0)} L ${getX(0)} ${getY(0)} Z`}
          fill="rgba(58, 15, 52, 0.08)"
        />

        {/* Depletion curve line */}
        <path
          d={pathD}
          fill="none"
          stroke="var(--color-deep-aubergine)"
          strokeWidth="3"
          strokeLinecap="round"
        />

        {/* Point at Day 0 */}
        <circle
          cx={getX(0)}
          cy={getY(initialStock)}
          r="4"
          fill="var(--color-marigold)"
          stroke="var(--color-deep-aubergine)"
          strokeWidth="2"
        />
        <text
          x={getX(0) + 6}
          y={getY(initialStock) - 6}
          fontSize="10"
          fontWeight="bold"
          fill="var(--color-deep-aubergine)"
          fontFamily="var(--font-mono)"
        >
          {initialStock}u
        </text>

        {/* X Axis labels */}
        <text x={getX(0)} y={svgHeight - 10} fontSize="10" fill="#7E6C7D" textAnchor="middle">
          Day 0
        </text>
        <text x={getX(10)} y={svgHeight - 10} fontSize="10" fill="#7E6C7D" textAnchor="middle">
          Day 10
        </text>
        <text x={getX(20)} y={svgHeight - 10} fontSize="10" fill="#7E6C7D" textAnchor="middle">
          Day 20
        </text>
        <text x={getX(30)} y={svgHeight - 10} fontSize="10" fill="#7E6C7D" textAnchor="middle">
          Day 30
        </text>

        {/* Y Axis labels */}
        <text x={padding.left - 8} y={getY(0) + 4} fontSize="10" fill="#7E6C7D" textAnchor="end" fontFamily="var(--font-mono)">
          0
        </text>
        <text x={padding.left - 8} y={getY(Math.round(maxStock / 2)) + 4} fontSize="10" fill="#7E6C7D" textAnchor="end" fontFamily="var(--font-mono)">
          {Math.round(maxStock / 2)}
        </text>
        <text x={padding.left - 8} y={getY(maxStock) + 4} fontSize="10" fill="#7E6C7D" textAnchor="end" fontFamily="var(--font-mono)">
          {maxStock}
        </text>
      </svg>
    </div>
  );
};
