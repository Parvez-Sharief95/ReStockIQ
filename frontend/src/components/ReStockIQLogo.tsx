import React from 'react';

interface ReStockIQLogoProps {
  size?: number;
  className?: string;
  showText?: boolean;
}

export const ReStockIQLogo: React.FC<ReStockIQLogoProps> = ({
  size = 36,
  className = '',
  showText = false,
}) => {
  return (
    <div
      className={`restockiq-logo-container ${className}`}
      style={{ display: 'inline-flex', alignItems: 'center', gap: '0.65rem' }}
    >
      <svg
        width={size}
        height={size}
        viewBox="0 0 48 48"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        role="img"
        aria-label="ReStockIQ Logo"
        style={{ flexShrink: 0, filter: 'drop-shadow(0 2px 6px rgba(58, 15, 52, 0.35))' }}
      >
        <title>ReStockIQ Logo</title>
        <defs>
          <linearGradient id="topFacet" x1="24" y1="4" x2="24" y2="20" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#7C3AED" />
            <stop offset="100%" stopColor="#5B21B6" />
          </linearGradient>
          <linearGradient id="leftFacet" x1="8" y1="14" x2="24" y2="38" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#4A154B" />
            <stop offset="100%" stopColor="#250821" />
          </linearGradient>
          <linearGradient id="rightFacet" x1="24" y1="20" x2="40" y2="38" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#4338CA" />
            <stop offset="100%" stopColor="#2E1065" />
          </linearGradient>
          <linearGradient id="arrowGradient" x1="16" y1="36" x2="34" y2="12" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#EAAA00" />
            <stop offset="100%" stopColor="#FBBF24" />
          </linearGradient>
        </defs>

        {/* Isometric 3D Box Facets */}
        {/* Top Face */}
        <polygon points="24,4 40,13 24,22 8,13" fill="url(#topFacet)" stroke="#8B5CF6" strokeWidth="1" />

        {/* Left Face */}
        <polygon points="8,13 24,22 24,40 8,31" fill="url(#leftFacet)" stroke="#5B21B6" strokeWidth="1" />

        {/* Right Face */}
        <polygon points="24,22 40,13 40,31 24,40" fill="url(#rightFacet)" stroke="#4338CA" strokeWidth="1" />

        {/* Intelligent Restocking Arrow / IQ Loop in Marigold */}
        <path
          d="M17 28 C 14 20, 20 12, 28 14 C 33 15, 36 20, 34 25 C 32 29, 27 32, 22 30"
          stroke="url(#arrowGradient)"
          strokeWidth="3.2"
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />
        {/* Arrowhead */}
        <polygon points="31,10 36,15 28,16" fill="#FBBF24" />

        {/* Intelligence Spark Point (IQ Node) */}
        <circle cx="21" cy="30" r="2.2" fill="#EAAA00" />
      </svg>

      {showText && (
        <span
          style={{
            fontWeight: 800,
            fontSize: `${size * 0.55}px`,
            letterSpacing: '-0.02em',
            color: '#FFFFFF',
            lineHeight: 1,
          }}
        >
          ReStock<span style={{ color: '#EAAA00' }}>IQ</span>
        </span>
      )}
    </div>
  );
};
