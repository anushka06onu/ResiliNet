import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import NetworkOverview from '../NetworkOverview';
import { useStore } from '../../store/useStore';

describe('NetworkOverview Component', () => {
  it('renders network overview with dynamic topology and stats', () => {
    useStore.setState({
      activeConnections: 3,
      dataMode: 'LIVE LAB',
      currentTopology: {
        topology_id: 'sndlib_backbone',
        nodes: [{ id: 's1' }, { id: 's2' }],
        links: [{ source: 's1', target: 's2' }],
        mode: 'LIVE LAB',
      },
      latestTelemetry: {
        experiment_id: 'exp_001_live',
        timestamp: '2026-08-27T12:00:00Z',
      },
    });

    render(<NetworkOverview />);

    expect(screen.getByText('Network Overview')).toBeDefined();
    expect(screen.getByText('sndlib_backbone')).toBeDefined();
    expect(screen.getByText('exp_001_live')).toBeDefined();
    expect(screen.getByText('3')).toBeDefined();
    expect(screen.getByText('MODE: LIVE LAB')).toBeDefined();
  });
});
