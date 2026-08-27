import { render, screen } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import RoutingDecisions from '../RoutingDecisions';
import * as api from '../../services/api';

vi.mock('../../services/api', () => ({
  getRoutingDecisions: vi.fn(),
}));

describe('RoutingDecisions', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('renders correctly and fetches routing decisions', async () => {
    vi.mocked(api.getRoutingDecisions).mockResolvedValue([
      {
        decision_id: 'd1',
        experiment_id: 'exp1',
        flow_id: 'f_1',
        timestamp: new Date().toISOString(),
        risk_before: 0.8,
        risk_after: 0.1,
        original_path: ['s1', 's2'],
        proposed_path: ['s1', 's3', 's2'],
        safeguard_result: 'Passed',
        installation_status: 'success',
        verification_status: 'success',
        outcome_status: 'success',
      },
    ]);

    render(<RoutingDecisions />);

    expect(screen.getByText('Routing Decisions Log')).toBeTruthy();

    expect(await screen.findByText('80/100')).toBeTruthy();
    expect(await screen.findByText('10/100')).toBeTruthy();
    expect((await screen.findAllByText('s1 → s2')).length).toBeGreaterThan(0);
    expect((await screen.findAllByText('s1 → s3 → s2')).length).toBeGreaterThan(0);
  });
});
