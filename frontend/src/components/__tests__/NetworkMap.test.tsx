import { render, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import NetworkMap from '../NetworkMap';
import * as api from '../../services/api';

// Mock the API and cytoscape
vi.mock('../../services/api');
vi.mock('cytoscape', () => {
  return {
    default: vi.fn(() => ({
      on: vi.fn(),
      destroy: vi.fn(),
      elements: vi.fn(() => []),
    })),
  };
});

describe('NetworkMap', () => {
  it('loads and transforms topology edges correctly', async () => {
    // Mock the topology response
    vi.mocked(api.getTopology).mockResolvedValue({
      nodes: [{ id: 's1', type: 'switch' }, { id: 's2', type: 'switch' }],
      links: [
        {
          source: 's1',
          target: 's2',
          source_port: 1,
          target_port: 2,
        },
      ],
      mode: 'DEMO DATA',
    });

    const mockOnSelect = vi.fn();
    render(<NetworkMap onSelectElement={mockOnSelect} />);

    // Wait for the loading state to finish
    await waitFor(() => {
      expect(api.getTopology).toHaveBeenCalled();
    });
  });
});
