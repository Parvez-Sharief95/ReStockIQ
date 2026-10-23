import React from 'react';

export const SyntheticBanner: React.FC = () => {
  return (
    <div className="synthetic-banner" role="status" aria-label="Synthetic Data Mode Active">
      <div className="synthetic-banner-inner">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
          <span className="synthetic-badge-pill">
            Synthetic Data Mode
          </span>
          <span>
            Operating against approved mock source adapters. Real procurement and live supplier order endpoints are completely isolated.
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem', fontSize: '0.78rem', color: '#EAAA00' }}>
          <span>Free-Tier Compliant</span>
          <span>•</span>
          <span>Zero Quota Spent</span>
        </div>
      </div>
    </div>
  );
};
