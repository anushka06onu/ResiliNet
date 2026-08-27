import { render, screen, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import FlowMonitor from '../FlowMonitor';
import * as api from '../../services/api';

vi.mock('../../services/api', () => ({
  getFlows: vi.fn(),
}));

describe('FlowMonitor', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('renders correctly and fetches flows', async () => {
    vi.mocked(api.getFlows).mockResolvedValue([
      {
        id: 'f_1',
        src: 'h1',
        dst: 'h4',
        category: 'Database Sync',
        tier: 'Critical',
        current_path: ['s1', 's2'],
        sla_status: 'Healthy',
        metrics: { latency_ms: 10, loss_percent: 0 },
        risk: '20%',
      },
    ]);

    render(<FlowMonitor />);

    expect(screen.getByText('Flow & SLA Monitor')).toBeTruthy();

    await waitFor(() => {
      expect(screen.getByText('f_1')).toBeTruthy();
      expect(screen.getByText('h1 → h4')).toBeTruthy();
      expect(screen.getByText('Database Sync')).toBeTruthy();
      expect(screen.getByText('10ms')).toBeTruthy();
    });
  });
});
