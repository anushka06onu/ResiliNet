import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import ExperimentControl from '../ExperimentControl';
import * as api from '../../services/api';

vi.mock('../../services/api');

describe('ExperimentControl Component', () => {
  it('renders simulation configuration panel and starts experiment', async () => {
    vi.mocked(api.getScenarios).mockResolvedValue(['normal', 'gradual_congestion', 'sudden_surge', 'concurrent_flows']);
    vi.mocked(api.getExperiments).mockResolvedValue([]);
    vi.mocked(api.startExperiment).mockResolvedValue({
      status: 'STARTING',
      experiment: 'exp_predictive_normal_ui',
      scenario: 'normal',
    });

    render(<ExperimentControl />);

    expect(screen.getByText('Simulation & Replay')).toBeDefined();
    expect(screen.getByText('Traffic Scenario')).toBeDefined();
    expect(screen.getByText('Routing Policy')).toBeDefined();

    const startBtn = screen.getByRole('button', { name: /^Start$/i });
    fireEvent.click(startBtn);

    await waitFor(() => {
      expect(api.startExperiment).toHaveBeenCalledWith(
        expect.objectContaining({
          scenario: 'normal',
          policy: 'predictive',
        }),
      );
    });
  });

  it('handles startExperiment failure gracefully', async () => {
    vi.mocked(api.getExperiments).mockResolvedValue([]);
    vi.mocked(api.startExperiment).mockRejectedValue(new Error('Network error'));

    render(<ExperimentControl />);

    const startBtn = screen.getByRole('button', { name: /^Start$/i });
    fireEvent.click(startBtn);

    await waitFor(() => {
      expect(screen.getByText('Error')).toBeDefined();
    });
  });
});
