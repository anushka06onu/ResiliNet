import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import SystemHealth from '../SystemHealth';
import { useStore } from '../../store/useStore';

describe('SystemHealth Component', () => {
  it('renders system health metrics when disconnected', () => {
    useStore.setState({
      wsConnected: false,
      dataMode: 'DISCONNECTED',
      latestTelemetry: null,
    });

    render(<SystemHealth />);

    expect(screen.getByText('System Health and Audit Log')).toBeDefined();
    expect(screen.getByText('Collector Status')).toBeDefined();
    expect(screen.getByText('Not connected')).toBeDefined();
    expect(screen.getByText('Disconnected')).toBeDefined();
  });

  it('renders system health metrics when connected in LIVE LAB mode', () => {
    useStore.setState({
      wsConnected: true,
      dataMode: 'LIVE LAB',
      latestTelemetry: { timestamp: '2026-08-27T12:00:00Z' },
    });

    render(<SystemHealth />);

    expect(screen.getAllByText('Connected').length).toBeGreaterThan(0);
    expect(screen.getByText('LIVE LAB')).toBeDefined();
  });
});
